import json
import secrets
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from urllib import request
import zipfile

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.cache import cache_page, never_cache
from django.http import (
    HttpResponse, JsonResponse, Http404, HttpResponseForbidden, 
    HttpResponseBadRequest, FileResponse
)
from django.urls import reverse, reverse_lazy
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.mail import send_mail, EmailMessage
from django.core.cache import cache
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q, Count, Avg, Sum, F
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.conf import settings
from django.template.loader import render_to_string

# Image processing
from PIL import Image, ImageDraw, ImageFont
import qrcode

# PDF generation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet

from .models import (
    AffiliationCard, CardTemplate, CardVerification, CardDelivery,
    CardStatusChange, CardSystemSettings
)
from .forms import (
    CardAssignmentForm, CardPhotoUploadForm, CardStatusUpdateForm,
    BulkCardOperationForm, CardLookupForm, QRVerificationForm,
    CardDeliveryForm, CardDownloadForm, CardTemplateForm,
    SystemSettingsForm, CardReportForm, ContactForm
)

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FUNCTIONS AND DECORATORS
# ============================================================================
def bulk_send_emails(cards, user, email_type='general', custom_subject=None, custom_message=None, request=None):
    """
    Bulk send emails to cardholders.
    
    Args:
        cards: QuerySet of AffiliationCard objects
        user: User performing the operation
        email_type: Type of email to send ('renewal_reminder', 'update', 'reactivation', 'welcome', 'custom')
        custom_subject: Custom email subject (for custom email type)
        custom_message: Custom email message (for custom email type)
    """
    success_count = 0
    failed_count = 0
    failed_emails = []
    
    for card in cards:
        try:
            # Skip cards without email addresses
            if not card.affiliate_email:
                failed_count += 1
                failed_emails.append(f"{card.card_number} - No email address")
                continue
            
            # Determine email content based on type
            if email_type == 'renewal_reminder':
                subject = f"ACRP Card Renewal Reminder - {card.card_number}"
                template = 'affiliationcard/emails/renewal_reminder.html'
                
            elif email_type == 'update':
                subject = f"ACRP Card System Update - {card.card_number}"
                template = 'affiliationcard/emails/system_update.html'
                
            elif email_type == 'reactivation':
                subject = f"Reactivate Your ACRP Card - {card.card_number}"
                template = 'affiliationcard/emails/reactivation.html'
                
            elif email_type == 'welcome':
                subject = f"Welcome to ACRP Digital Cards - {card.card_number}"
                template = 'affiliationcard/emails/welcome.html'
                
            elif email_type == 'custom':
                subject = custom_subject or f"ACRP Card Communication - {card.card_number}"
                template = 'affiliationcard/emails/custom.html'
                
            else:
                subject = f"ACRP Card Information - {card.card_number}"
                template = 'affiliationcard/emails/general.html'
            
            # Prepare email context
            context = {
                'card': card,
                'user': user,
                'email_type': email_type,
                'custom_message': custom_message,
                'current_year': timezone.now().year,
                'verification_url': request.build_absolute_uri(
                    reverse('affiliationcard:verify_token', args=[card.verification_token])
                ) if request else '#',
                'card_detail_url': request.build_absolute_uri(
                    reverse('affiliationcard:download_card', args=[card.verification_token])
                ) if request else '#',
            }
            
            # Render email content
            message = render_to_string(template, context)
            
            # Send email
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[card.affiliate_email]
            )
            email.content_subtype = "html"
            email.send()
            
            success_count += 1
            
            # Log the email sending
            logger.info(f"Bulk email sent to {card.affiliate_email} for card {card.card_number} by {user.username}")
            
        except Exception as e:
            failed_count += 1
            failed_emails.append(f"{card.card_number} - {str(e)}")
            logger.error(f"Failed to send bulk email for card {card.card_number}: {e}")
    
    # Prepare result message
    message = f'{success_count} emails sent successfully'
    if failed_count > 0:
        message += f', {failed_count} failed'
    
    return {
        'message': message,
        'success_count': success_count,
        'failed_count': failed_count,
        'failed_emails': failed_emails
    }


def bulk_regenerate_cards(cards, user, reason='bulk_regeneration', regenerate_tokens=True, regenerate_numbers=False, update_template=None):
    """
    Bulk regenerate card data (tokens, numbers, templates).
    
    Args:
        cards: QuerySet of AffiliationCard objects
        user: User performing the operation
        reason: Reason for regeneration
        regenerate_tokens: Whether to regenerate verification tokens
        regenerate_numbers: Whether to regenerate card numbers
        update_template: New template to apply (CardTemplate instance)
    """
    success_count = 0
    failed_count = 0
    failed_cards = []
    
    with transaction.atomic():
        for card in cards:
            try:
                old_data = {
                    'card_number': card.card_number,
                    'verification_token': card.verification_token,
                    'template': card.card_template.name if card.card_template else None
                }
                
                # Regenerate verification token
                if regenerate_tokens:
                    card.verification_token = secrets.token_urlsafe(32)
                
                # Regenerate card number (be careful with this!)
                if regenerate_numbers:
                    # Generate new card number using the same pattern as original
                    new_card_number = card.generate_card_number()
                    
                    # Ensure uniqueness
                    while AffiliationCard.objects.filter(card_number=new_card_number).exists():
                        new_card_number = card.generate_card_number()
                    
                    card.card_number = new_card_number
                
                # Update template if provided
                if update_template:
                    card.card_template = update_template
                
                # Update timestamps
                card.updated_at = timezone.now()
                card.save()
                
                # Log the regeneration
                CardStatusChange.objects.create(
                    card=card,
                    old_status=card.status,
                    new_status=card.status,  # Status doesn't change
                    reason=f"Bulk regeneration: {reason}",
                    changed_by=user,
                    ip_address='127.0.0.1',  # System operation
                    user_agent='System/BulkRegeneration',
                    additional_data=json.dumps({
                        'operation': 'bulk_regeneration',
                        'regenerated_tokens': regenerate_tokens,
                        'regenerated_numbers': regenerate_numbers,
                        'old_card_number': old_data['card_number'],
                        'old_verification_token': old_data['verification_token'][:10] + '...',  # Partial for security
                        'new_template': update_template.name if update_template else None
                    })
                )
                
                success_count += 1
                
                logger.info(f"Card {card.card_number} regenerated by {user.username}: {reason}")
                
            except Exception as e:
                failed_count += 1
                failed_cards.append(f"{card.card_number} - {str(e)}")
                logger.error(f"Failed to regenerate card {card.card_number}: {e}")
    
    # Prepare result message
    message = f'{success_count} cards regenerated successfully'
    if failed_count > 0:
        message += f', {failed_count} failed'
    
    return {
        'message': message,
        'success_count': success_count,
        'failed_count': failed_count,
        'failed_cards': failed_cards
    }


def bulk_send_emails_with_attachments(cards, user, email_type='card_delivery', attachment_format='pdf'):
    """
    Bulk send emails with card attachments.
    
    This is a specialized version for sending actual card files.
    """
    success_count = 0
    failed_count = 0
    failed_emails = []
    
    for card in cards:
        try:
            if not card.affiliate_email:
                failed_count += 1
                failed_emails.append(f"{card.card_number} - No email address")
                continue
            
            # Generate card file
            file_content, filename, content_type = generate_card_file(card, attachment_format)
            
            # Prepare email
            subject = f"Your ACRP Digital Card - {card.card_number}"
            context = {
                'card': card,
                'user': user
            }
            
            message = render_to_string('affiliationcard/emails/card_delivery.html', context)
            
            # Create email with attachment
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[card.affiliate_email]
            )
            email.content_subtype = "html"
            email.attach(filename, file_content, content_type)
            
            # Send email
            email.send()
            
            success_count += 1
            
            # Create delivery record
            CardDelivery.objects.create(
                card=card,
                delivery_type='email_pdf',
                recipient_email=card.affiliate_email,
                recipient_name=card.get_display_name(),
                initiated_by=user,
                file_format=attachment_format,
                status='completed',
                completed_at=timezone.now()
            )
            
            logger.info(f"Card attachment sent to {card.affiliate_email} for card {card.card_number}")
            
        except Exception as e:
            failed_count += 1
            failed_emails.append(f"{card.card_number} - {str(e)}")
            logger.error(f"Failed to send card attachment for {card.card_number}: {e}")
    
    message = f'{success_count} card emails sent successfully'
    if failed_count > 0:
        message += f', {failed_count} failed'
    
    return {
        'message': message,
        'success_count': success_count,
        'failed_count': failed_count,
        'failed_emails': failed_emails
    }


# Helper function to add to your existing bulk_operations view
def handle_bulk_send_emails(request, cards, form_data):
    """
    Handle bulk email sending with different options.
    """
    email_type = form_data.get('email_type', 'general')
    custom_subject = form_data.get('custom_subject')
    custom_message = form_data.get('custom_message')
    include_attachment = form_data.get('include_attachment', False)
    attachment_format = form_data.get('attachment_format', 'pdf')
    
    if include_attachment:
        return bulk_send_emails_with_attachments(cards, request.user, email_type, attachment_format)
    else:
        return bulk_send_emails(cards, request.user, email_type, custom_subject, custom_message)


def handle_bulk_regenerate_cards(request, cards, form_data):
    """
    Handle bulk card regeneration with different options.
    """
    reason = form_data.get('reason', 'Bulk regeneration')
    regenerate_tokens = form_data.get('regenerate_tokens', True)
    regenerate_numbers = form_data.get('regenerate_numbers', False)
    template_id = form_data.get('new_template_id')
    
    update_template = None
    if template_id:
        try:
            update_template = CardTemplate.objects.get(id=template_id)
        except CardTemplate.DoesNotExist:
            pass
    
    return bulk_regenerate_cards(
        cards, request.user, reason, 
        regenerate_tokens, regenerate_numbers, update_template
    )

def is_card_admin(user):
    """Check if user has card administration privileges."""
    return user.is_staff or user.acrp_role in {
        'GLOBAL_SDP', 'PROVIDER_ADMIN'
    }


def get_client_ip(request):
    """Extract client IP address safely."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def rate_limit_verification(request, max_attempts=10, window_minutes=60):
    """Simple rate limiting for verification attempts."""
    ip = get_client_ip(request)
    cache_key = f"card_verification_attempts:{ip}"
    
    attempts = cache.get(cache_key, 0)
    if attempts >= max_attempts:
        return False
    
    cache.set(cache_key, attempts + 1, window_minutes * 60)
    return True


# ============================================================================
# ADMIN CARD MANAGEMENT VIEWS
# ============================================================================

@login_required
@user_passes_test(is_card_admin)
def card_dashboard(request):
    """
    Main dashboard for card administration.
    
    Shows overview statistics, recent activity, and quick actions.
    """
    # Get summary statistics
    stats = {
        'total_cards': AffiliationCard.objects.count(),
        'active_cards': AffiliationCard.objects.filter(status='active').count(),
        'pending_cards': AffiliationCard.objects.filter(status='pending_assignment').count(),
        'expired_cards': AffiliationCard.objects.filter(status='expired').count(),
        'total_verifications': CardVerification.objects.count(),
        'recent_verifications': CardVerification.objects.filter(
            verified_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
    }
    
    # Council breakdown
    council_stats = AffiliationCard.objects.values('council_code').annotate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        pending=Count('id', filter=Q(status='pending_assignment'))
    ).order_by('council_code')
    
    # Recent cards
    recent_cards = AffiliationCard.objects.select_related().order_by('-created_at')[:10]
    
    # Recent verifications
    recent_verifications = CardVerification.objects.select_related('card').order_by('-verified_at')[:10]
    
    # Cards expiring soon (next 30 days)
    expiring_soon = AffiliationCard.objects.filter(
        status='active',
        date_expires__lte=timezone.now().date() + timedelta(days=30),
        date_expires__gte=timezone.now().date()
    ).order_by('date_expires')[:10]
    
    context = {
        'stats': stats,
        'council_stats': council_stats,
        'recent_cards': recent_cards,
        'recent_verifications': recent_verifications,
        'expiring_soon': expiring_soon,
        'page_title': 'Card Administration Dashboard'
    }
    
    return render(request, 'affiliationcard/admin/dashboard.html', context)


@login_required
@user_passes_test(is_card_admin)
@require_http_methods(["GET", "POST"])
def assign_card(request, content_type_id, object_id):
    """
    Assign digital card to approved application.
    
    This is the main view called when admin clicks "Assign Digital Card"
    during application review in the enrollments app.
    """
    # Get the application
    try:
        content_type = ContentType.objects.get(pk=content_type_id)
        application = content_type.get_object_for_this_type(pk=object_id)
    except (ContentType.DoesNotExist, application.DoesNotExist):
        messages.error(request, "Application not found.")
        return redirect('enrollments:application_list')
    
    # Validate application is approved
    if not hasattr(application, 'status') or application.status != 'approved':
        messages.error(request, "Card can only be assigned to approved applications.")
        return redirect('enrollments:application_detail', pk=object_id, app_type=application.get_affiliation_type())
    
    # Check if card already exists
    existing_card = AffiliationCard.objects.filter(
        content_type=content_type,
        object_id=object_id,
        status__in=['assigned', 'active']
    ).first()
    
    if existing_card:
        messages.warning(request, f"Card already exists: {existing_card.card_number}")
        return redirect('affiliationcard:card_detail', pk=existing_card.pk)
    
    # Get council for template filtering
    council = application.get_council()
    
    if request.method == 'POST':
        form = CardAssignmentForm(request.POST, council=council, application=application)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create the card
                    card = AffiliationCard.objects.create(
                        content_type=content_type,
                        object_id=object_id,
                        card_template=form.cleaned_data.get('card_template'),
                        grace_period_days=form.cleaned_data['grace_period_days'],
                        assigned_by=request.user,
                        assigned_at=timezone.now(),
                        status='assigned'
                    )
                    
                    # Issue immediately if requested
                    if form.cleaned_data['issue_immediately']:
                        card.issue_card(issued_by=request.user)
                        messages.success(request, f"Card {card.card_number} assigned and issued successfully!")
                    else:
                        messages.success(request, f"Card {card.card_number} assigned successfully!")
                    
                    # Send email notification if requested
                    if form.cleaned_data['send_email_notification']:
                        try:
                            send_card_assignment_notification(card)
                            messages.info(request, "Email notification sent to affiliate.")
                        except Exception as e:
                            logger.error(f"Failed to send card notification: {e}")
                            messages.warning(request, "Card created but email notification failed.")
                    
                    return redirect('affiliationcard:card_detail', pk=card.pk)
                    
            except Exception as e:
                logger.error(f"Error assigning card: {e}")
                messages.error(request, "An error occurred while assigning the card.")
    else:
        form = CardAssignmentForm(council=council, application=application)
    
    context = {
        'form': form,
        'application': application,
        'council': council,
        'page_title': f'Assign Card - {application.get_display_name()}'
    }
    
    return render(request, 'affiliationcard/admin/assign_card.html', context)


class CardListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """List view for all affiliation cards with filtering and search."""
    
    model = AffiliationCard
    template_name = 'affiliationcard/admin/card_list.html'
    context_object_name = 'cards'
    paginate_by = 25
    permission_required = 'affiliationcard.view_affiliationcard'
    
    def get_queryset(self):
        """Get filtered queryset based on search parameters."""
        queryset = AffiliationCard.objects.select_related().order_by('-created_at')
        
        # Apply filters
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(card_number__icontains=search) |
                Q(affiliate_full_name__icontains=search) |
                Q(affiliate_surname__icontains=search) |
                Q(affiliate_email__icontains=search)
            )
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        council = self.request.GET.get('council')
        if council:
            queryset = queryset.filter(council_code=council)
        
        affiliation_type = self.request.GET.get('affiliation_type')
        if affiliation_type:
            queryset = queryset.filter(affiliation_type=affiliation_type)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """Add filter options to context."""
        context = super().get_context_data(**kwargs)
        
        # Add filter choices
        context.update({
            'status_choices': AffiliationCard.STATUS_CHOICES,
            'council_choices': AffiliationCard.objects.values_list('council_code', 'council_name').distinct(),
            'affiliation_type_choices': AffiliationCard.objects.values_list('affiliation_type', 'affiliation_type').distinct(),
            'search_query': self.request.GET.get('search', ''),
            'selected_status': self.request.GET.get('status', ''),
            'selected_council': self.request.GET.get('council', ''),
            'selected_affiliation_type': self.request.GET.get('affiliation_type', ''),
            'page_title': 'Affiliation Cards'
        })
        
        return context


class CardDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Detailed view of a single affiliation card."""
    
    model = AffiliationCard
    template_name = 'affiliationcard/admin/card_detail.html'
    context_object_name = 'card'
    permission_required = 'affiliationcard.view_affiliationcard'
    
    def get_object(self):
        """Get card with related data."""
        return get_object_or_404(
            AffiliationCard.objects.select_related('card_template').prefetch_related(
                'verifications', 'deliveries', 'status_changes'
            ),
            pk=self.kwargs['pk']
        )
    
    def get_context_data(self, **kwargs):
        """Add additional context data."""
        context = super().get_context_data(**kwargs)
        card = self.object
        
        # Recent activity
        recent_verifications = card.verifications.order_by('-verified_at')[:10]
        recent_deliveries = card.deliveries.order_by('-initiated_at')[:5]
        status_history = card.status_changes.order_by('-changed_at')[:10]
        
        # Statistics
        verification_stats = {
            'total': card.total_verifications,
            'last_30_days': card.verifications.filter(
                verified_at__gte=timezone.now() - timedelta(days=30)
            ).count(),
            'last_7_days': card.verifications.filter(
                verified_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
        }
        
        context.update({
            'recent_verifications': recent_verifications,
            'recent_deliveries': recent_deliveries,
            'status_history': status_history,
            'verification_stats': verification_stats,
            'page_title': f'Card {card.card_number}'
        })
        
        return context


@login_required
@user_passes_test(is_card_admin)
@require_POST
def update_card_status(request, pk):
    """Update card status (activate, suspend, revoke, etc.)."""
    card = get_object_or_404(AffiliationCard, pk=pk)
    form = CardStatusUpdateForm(request.POST, card=card)
    
    if form.is_valid():
        try:
            old_status = card.status
            new_status = form.cleaned_data['new_status']
            reason = form.cleaned_data['reason']
            
            with transaction.atomic():
                # Update card status
                card.status = new_status
                card.save()
                
                # Log status change
                CardStatusChange.objects.create(
                    card=card,
                    old_status=old_status,
                    new_status=new_status,
                    reason=reason,
                    changed_by=request.user,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                # Send notification if requested
                if form.cleaned_data['notify_affiliate']:
                    try:
                        send_status_change_notification(card, old_status, new_status, reason)
                    except Exception as e:
                        logger.error(f"Failed to send status change notification: {e}")
                        messages.warning(request, "Status updated but notification failed.")
                
                messages.success(request, f"Card status updated to {card.get_status_display()}")
                
        except Exception as e:
            logger.error(f"Error updating card status: {e}")
            messages.error(request, "Failed to update card status.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    
    return redirect('affiliationcard:card_detail', pk=pk)


@login_required
@user_passes_test(is_card_admin)
def bulk_operations(request):
    """Handle bulk operations on multiple cards."""
    if request.method == 'POST':
        form = BulkCardOperationForm(request.POST)
        
        if form.is_valid():
            operation = form.cleaned_data['operation']
            card_ids = form.cleaned_data['card_ids']
            reason = form.cleaned_data.get('reason', '')
            send_notifications = form.cleaned_data['send_notifications']
            
            cards = AffiliationCard.objects.filter(id__in=card_ids)
            
            try:
                with transaction.atomic():
                    if operation == 'assign':
                        result = bulk_assign_cards(cards, request.user, reason, request=request)
                    elif operation == 'issue':
                        result = bulk_issue_cards(cards, request.user, reason, request=request)
                    elif operation == 'suspend':
                        result = bulk_suspend_cards(cards, request.user, reason, request=request)
                    elif operation == 'send_email':
                        result = bulk_send_emails(cards, request.user, request=request)
                    elif operation == 'regenerate':
                        result = bulk_regenerate_cards(cards, request.user, request=request)
                    else:
                        messages.error(request, "Invalid operation")
                        return redirect('affiliationcard:card_list')
                    
                    messages.success(request, f"Bulk operation completed: {result['message']}")
                    
            except Exception as e:
                logger.error(f"Bulk operation failed: {e}")
                messages.error(request, "Bulk operation failed.")
        else:
            messages.error(request, "Invalid form data.")
    
    return redirect('affiliationcard:card_list')


# ============================================================================
# PUBLIC VERIFICATION VIEWS
# ============================================================================

@never_cache
def verify_lookup(request):
    """
    Public card lookup/verification by card number.
    
    This is the main public verification page where anyone can
    enter a card number to verify affiliate status.
    """
    if not rate_limit_verification(request):
        return render(request, 'affiliationcard/public/rate_limited.html', status=429)
    
    verification_result = None
    
    if request.method == 'POST':
        form = CardLookupForm(request.POST)
        
        if form.is_valid():
            card_number = form.cleaned_data['card_number']
            purpose = form.cleaned_data.get('verification_purpose', '')
            
            try:
                # Find the card
                card = AffiliationCard.objects.get(card_number=card_number)
                
                # Record verification
                verification = CardVerification.objects.create(
                    card=card,
                    verification_type='manual_lookup',
                    verified_at=timezone.now(),
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    was_successful=True,
                    card_status_at_time=card.status,
                    verification_purpose=purpose
                )
                
                # Update card verification count
                card.increment_verification_count()
                
                verification_result = {
                    'success': True,
                    'card': card,
                    'verification': verification
                }
                
            except AffiliationCard.DoesNotExist:
                verification_result = {
                    'success': False,
                    'error': 'Card not found',
                    'message': 'No card found with this number. Please check the card number and try again.'
                }
            except Exception as e:
                logger.error(f"Verification error: {e}")
                verification_result = {
                    'success': False,
                    'error': 'system_error',
                    'message': 'System error occurred during verification. Please try again later.'
                }
    else:
        form = CardLookupForm()
    
    context = {
        'form': form,
        'verification_result': verification_result,
        'page_title': 'Verify Affiliation Card'
    }
    
    return render(request, 'affiliationcard/public/verify_lookup.html', context)


@never_cache
def verify_token(request, token):
    """
    Verify card using QR code verification token.
    
    This is called when someone scans a QR code on a card.
    """
    if not rate_limit_verification(request):
        return render(request, 'affiliationcard/public/rate_limited.html', status=429)
    
    try:
        # Find card by verification token
        card = AffiliationCard.objects.get(verification_token=token)
        
        # Record verification
        verification = CardVerification.objects.create(
            card=card,
            verification_type='qr_scan',
            verified_at=timezone.now(),
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=request.META.get('HTTP_REFERER', ''),
            was_successful=True,
            card_status_at_time=card.status
        )
        
        # Update card verification count
        card.increment_verification_count()
        
        verification_result = {
            'success': True,
            'card': card,
            'verification': verification
        }
        
    except AffiliationCard.DoesNotExist:
        verification_result = {
            'success': False,
            'error': 'invalid_token',
            'message': 'Invalid verification token. This may be a counterfeit card.'
        }
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        verification_result = {
            'success': False,
            'error': 'system_error',
            'message': 'System error occurred during verification.'
        }
    
    context = {
        'verification_result': verification_result,
        'page_title': 'Card Verification Result'
    }
    
    return render(request, 'affiliationcard/public/verification_result.html', context)


@csrf_exempt
@require_POST
def api_verify(request):
    """
    API endpoint for card verification.
    
    Returns JSON response for programmatic verification.
    """
    if not rate_limit_verification(request):
        return JsonResponse({
            'success': False,
            'error': 'rate_limit_exceeded',
            'message': 'Too many verification attempts. Please try again later.'
        }, status=429)
    
    try:
        # Parse request data
        data = json.loads(request.body)
        card_number = data.get('card_number')
        token = data.get('verification_token')
        
        if not (card_number or token):
            return JsonResponse({
                'success': False,
                'error': 'missing_parameters',
                'message': 'Either card_number or verification_token is required'
            }, status=400)
        
        # Find card
        if token:
            card = AffiliationCard.objects.get(verification_token=token)
        else:
            card = AffiliationCard.objects.get(card_number=card_number)
        
        # Record verification
        verification = CardVerification.objects.create(
            card=card,
            verification_type='api_verification',
            verified_at=timezone.now(),
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            was_successful=True,
            card_status_at_time=card.status,
            verification_purpose=data.get('purpose', '')
        )
        
        # Update verification count
        card.increment_verification_count()
        
        # Return card information
        return JsonResponse({
            'success': True,
            'card': {
                'card_number': card.card_number,
                'affiliate_name': card.get_display_name(),
                'council': card.council_code,
                'affiliation_type': card.affiliation_type,
                'status': card.status,
                'is_active': card.is_active(),
                'is_expired': card.is_expired(),
                'date_issued': card.date_issued.isoformat() if card.date_issued else None,
                'date_expires': card.date_expires.isoformat() if card.date_expires else None,
                'days_until_expiry': card.days_until_expiry()
            },
            'verification_id': verification.id
        })
        
    except AffiliationCard.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'card_not_found',
            'message': 'Card not found'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'invalid_json',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"API verification error: {e}")
        return JsonResponse({
            'success': False,
            'error': 'system_error',
            'message': 'System error occurred'
        }, status=500)


# ============================================================================
# CARD DELIVERY VIEWS
# ============================================================================

@login_required
@user_passes_test(is_card_admin)
def send_card(request, pk):
    """Configure and send card to affiliate via email."""
    card = get_object_or_404(AffiliationCard, pk=pk)
    
    if request.method == 'POST':
        form = CardDeliveryForm(request.POST, card=card)
        
        if form.is_valid():
            try:
                delivery = create_card_delivery(
                    card=card,
                    delivery_method=form.cleaned_data['delivery_method'],
                    recipient_email=form.cleaned_data['recipient_email'],
                    recipient_name=form.cleaned_data['recipient_name'],
                    email_subject=form.cleaned_data['email_subject'],
                    email_message=form.cleaned_data['email_message'],
                    file_format=form.cleaned_data['file_format'],
                    initiated_by=request.user
                )
                
                messages.success(request, f"Card delivery initiated successfully! Delivery ID: {delivery.id}")
                return redirect('affiliationcard:card_detail', pk=pk)
                
            except Exception as e:
                logger.error(f"Card delivery error: {e}")
                messages.error(request, "Failed to initiate card delivery.")
    else:
        form = CardDeliveryForm(card=card)
    
    context = {
        'form': form,
        'card': card,
        'page_title': f'Send Card {card.card_number}'
    }
    
    return render(request, 'affiliationcard/admin/send_card.html', context)


@never_cache
def download_card(request, token):
    """Secure card download using token."""
    try:
        delivery = get_object_or_404(CardDelivery, download_token=token)
        
        if not delivery.is_download_valid():
            return render(request, 'affiliationcard/public/download_expired.html', {
                'delivery': delivery,
                'page_title': 'Download Expired'
            })
        
        if request.method == 'POST':
            form = CardDownloadForm(request.POST)
            form.fields['download_token'].initial = token
            
            if form.is_valid():
                file_format = form.cleaned_data['file_format']
                
                try:
                    # Generate card file
                    file_content, filename, content_type = generate_card_file(
                        delivery.card, file_format
                    )
                    
                    # Record download
                    delivery.record_download()
                    
                    # Return file
                    response = HttpResponse(file_content, content_type=content_type)
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
                    
                except Exception as e:
                    logger.error(f"Card generation error: {e}")
                    messages.error(request, "Failed to generate card file.")
        else:
            form = CardDownloadForm(initial={'download_token': token})
        
        context = {
            'form': form,
            'delivery': delivery,
            'card': delivery.card,
            'page_title': 'Download Your Card'
        }
        
        return render(request, 'affiliationcard/public/download_card.html', context)
        
    except CardDelivery.DoesNotExist:
        return render(request, 'affiliationcard/public/download_invalid.html', {
            'page_title': 'Invalid Download Link'
        })


# ============================================================================
# SYSTEM ADMINISTRATION VIEWS
# ============================================================================

class CardTemplateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """List all card templates."""
    
    model = CardTemplate
    template_name = 'affiliationcard/admin/template_list.html'
    context_object_name = 'templates'
    permission_required = 'affiliationcard.view_cardtemplate'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Card Templates'
        return context


class CardTemplateCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create new card template."""
    
    model = CardTemplate
    form_class = CardTemplateForm
    template_name = 'affiliationcard/admin/template_form.html'
    permission_required = 'affiliationcard.add_cardtemplate'
    success_url = reverse_lazy('affiliationcard:template_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Card template created successfully!")
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Create Card Template'
        return context


@login_required
@user_passes_test(lambda u: u.is_superuser)
def system_settings(request):
    """Manage system settings."""
    settings_obj = CardSystemSettings.get_settings()
    
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=settings_obj)
        
        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()
            messages.success(request, "System settings updated successfully!")
            return redirect('affiliationcard:system_settings')
    else:
        form = SystemSettingsForm(instance=settings_obj)
    
    context = {
        'form': form,
        'settings': settings_obj,
        'page_title': 'Card System Settings'
    }
    
    return render(request, 'affiliationcard/admin/system_settings.html', context)


# ============================================================================
# REPORTING AND ANALYTICS VIEWS
# ============================================================================

@login_required
@user_passes_test(is_card_admin)
def analytics_dashboard(request):
    """Analytics dashboard with charts and statistics."""
    
    # Date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Card statistics
    card_stats = {
        'total': AffiliationCard.objects.count(),
        'active': AffiliationCard.objects.filter(status='active').count(),
        'pending': AffiliationCard.objects.filter(status='pending_assignment').count(),
        'expired': AffiliationCard.objects.filter(status='expired').count(),
        'suspended': AffiliationCard.objects.filter(status='suspended').count(),
    }
    
    # Verification statistics
    verification_stats = {
        'total': CardVerification.objects.count(),
        'last_30_days': CardVerification.objects.filter(
            verified_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        'qr_scans': CardVerification.objects.filter(verification_type='qr_scan').count(),
        'manual_lookups': CardVerification.objects.filter(verification_type='manual_lookup').count(),
    }
    
    # Council breakdown
    council_breakdown = AffiliationCard.objects.values('council_code', 'council_name').annotate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active'))
    ).order_by('council_code')
    
    # Daily verification trend (last 30 days)
    daily_verifications = []
    for i in range(30):
        date = end_date - timedelta(days=i)
        count = CardVerification.objects.filter(
            verified_at__date=date
        ).count()
        daily_verifications.append({
            'date': date.isoformat(),
            'count': count
        })
    daily_verifications.reverse()
    
    context = {
        'card_stats': card_stats,
        'verification_stats': verification_stats,
        'council_breakdown': council_breakdown,
        'daily_verifications': daily_verifications,
        'date_range': f"{start_date} to {end_date}",
        'page_title': 'Card Analytics'
    }
    
    return render(request, 'affiliationcard/admin/analytics.html', context)


@login_required
@user_passes_test(is_card_admin)
def generate_report(request):
    """Generate custom reports."""
    if request.method == 'POST':
        form = CardReportForm(request.POST)
        
        if form.is_valid():
            report_data = create_custom_report(form.cleaned_data)
            
            output_format = form.cleaned_data['output_format']
            
            if output_format == 'pdf':
                return generate_pdf_report(report_data)
            elif output_format == 'csv':
                return generate_csv_report(report_data)
            elif output_format == 'excel':
                return generate_excel_report(report_data)
            else:
                context = {
                    'report_data': report_data,
                    'form': form,
                    'page_title': 'Card Report'
                }
                return render(request, 'affiliationcard/admin/report_results.html', context)
    else:
        form = CardReportForm()
    
    context = {
        'form': form,
        'page_title': 'Generate Report'
    }
    
    return render(request, 'affiliationcard/admin/generate_report.html', context)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def send_card_assignment_notification(card, request):
    """Send email notification when card is assigned."""
    subject = f"Your ACRP Digital Affiliation Card is Ready - {card.card_number}"
    
    context = {
        'card': card,
        'download_url': request.build_absolute_uri(
            reverse('affiliationcard:download_card', args=[card.verification_token])
        )
    }
    
    message = render_to_string('affiliationcard/emails/card_assigned.html', context)
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[card.affiliate_email],
        html_message=message
    )


def send_status_change_notification(card, old_status, new_status, reason):
    """Send notification when card status changes."""
    subject = f"ACRP Card Status Update - {card.card_number}"
    
    context = {
        'card': card,
        'old_status': old_status,
        'new_status': new_status,
        'reason': reason
    }
    
    message = render_to_string('affiliationcard/emails/status_change.html', context)
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[card.affiliate_email],
        html_message=message
    )


def create_card_delivery(card, delivery_method, recipient_email, recipient_name, **kwargs):
    """Create and process card delivery."""
    delivery = CardDelivery.objects.create(
        card=card,
        delivery_type=delivery_method,
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        initiated_by=kwargs.get('initiated_by'),
        file_format=kwargs.get('file_format', 'pdf')
    )
    
    # Process delivery based on method
    if delivery_method == 'email_pdf':
        process_email_pdf_delivery(delivery, kwargs)
    elif delivery_method == 'email_link':
        process_email_link_delivery(delivery, kwargs)
    elif delivery_method == 'direct_download':
        process_direct_download_delivery(delivery, kwargs)
    
    return delivery


def generate_card_file(card, file_format):
    """Generate card file in specified format."""
    if file_format == 'pdf':
        return generate_card_pdf(card)
    elif file_format == 'png':
        return generate_card_image(card, 'PNG')
    elif file_format == 'jpg':
        return generate_card_image(card, 'JPEG')
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def generate_card_pdf(card):
    """Generate PDF version of the card."""
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    
    # Add card content (implementation depends on your design requirements)
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"ACRP Digital Affiliation Card", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Card details
    details = f"""
    <b>Card Number:</b> {card.card_number}<br/>
    <b>Name:</b> {card.get_display_name()}<br/>
    <b>Council:</b> {card.council_name}<br/>
    <b>Affiliation:</b> {card.affiliation_type.title()}<br/>
    <b>Issued:</b> {card.date_issued.strftime('%Y-%m-%d') if card.date_issued else 'Not issued'}<br/>
    <b>Expires:</b> {card.date_expires.strftime('%Y-%m-%d') if card.date_expires else 'No expiry'}<br/>
    <b>Status:</b> {card.get_status_display()}
    """
    
    content = Paragraph(details, styles['Normal'])
    story.append(content)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    filename = f"ACRP_Card_{card.card_number}.pdf"
    content_type = 'application/pdf'
    
    return buffer.getvalue(), filename, content_type


def generate_card_image(card, format):
    """Generate image version of the card."""
    # Create card image (simplified version - enhance based on your design)
    img = Image.new('RGB', (850, 540), color='white')
    draw = ImageDraw.Draw(img)
    
    # Add card content (basic version)
    draw.text((50, 50), f"ACRP Digital Card", fill='black')
    draw.text((50, 100), f"Card #: {card.card_number}", fill='black')
    draw.text((50, 150), f"Name: {card.get_display_name()}", fill='black')
    draw.text((50, 200), f"Council: {card.council_name}", fill='black')
    draw.text((50, 250), f"Status: {card.get_status_display()}", fill='black')
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=3, border=4)
    qr.add_data(card.qr_code_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Paste QR code on card
    img.paste(qr_img, (650, 350))
    
    # Save to buffer
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    
    filename = f"ACRP_Card_{card.card_number}.{format.lower()}"
    content_type = f'image/{format.lower()}'
    
    return buffer.getvalue(), filename, content_type


# Bulk operation functions
def bulk_assign_cards(cards, user, reason):
    """Bulk assign cards."""
    count = 0
    for card in cards:
        if card.status == 'pending_assignment':
            card.assign_card(assigned_by=user)
            count += 1
    
    return {'message': f'{count} cards assigned successfully'}


def bulk_issue_cards(cards, user, reason):
    """Bulk issue cards."""
    count = 0
    for card in cards:
        if card.status == 'assigned':
            card.issue_card(issued_by=user)
            count += 1
    
    return {'message': f'{count} cards issued successfully'}


def bulk_suspend_cards(cards, user, reason):
    """Bulk suspend cards."""
    count = 0
    for card in cards:
        if card.status == 'active':
            card.suspend_card(reason=reason)
            count += 1
    
    return {'message': f'{count} cards suspended successfully'}


def process_email_pdf_delivery(delivery, kwargs):
    """Process email delivery with PDF attachment."""
    # Implementation for email with PDF attachment
    pass


def process_email_link_delivery(delivery, kwargs):
    """Process email delivery with download link."""
    # Implementation for email with download link
    pass


def process_direct_download_delivery(delivery, kwargs):
    """Process direct download generation."""
    # Implementation for direct download
    pass


def create_custom_report(form_data):
    """Create custom report based on form data."""
    # Implementation for custom report generation
    return {}


def generate_pdf_report(report_data):
    """Generate PDF report."""
    # Implementation for PDF report generation
    pass


def generate_csv_report(report_data):
    """Generate CSV report."""
    # Implementation for CSV report generation
    pass


def generate_excel_report(report_data):
    """Generate Excel report."""
    # Implementation for Excel report generation
    pass