from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg, F, Case, When, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponse, Http404, HttpResponseForbidden
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, 
    TemplateView, FormView
)
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.urls import reverse_lazy, reverse
from django.template.loader import render_to_string
from django.conf import settings
from datetime import datetime, timedelta
from decimal import Decimal
import json
import csv
from io import StringIO, BytesIO

from .models import (
    CPDProvider, CPDCategory, CPDRequirement, CPDActivity, 
    CPDPeriod, CPDRecord, CPDEvidence, CPDApproval, 
    CPDCompliance, CPDCertificate, CPDAuditLog
)
from .forms import (
    CPDProviderForm, CPDCategoryForm, CPDRequirementForm, CPDActivityForm,
    UserCPDActivityForm, CPDRecordForm, CPDEvidenceForm, CPDApprovalForm,
    BulkApprovalForm, CPDActivitySearchForm, CPDRecordFilterForm,
    ComplianceReportForm, QuickRegistrationForm, QuickFeedbackForm
)
from .utils import (
    calculate_user_compliance, generate_compliance_certificate,
    send_approval_notification, log_cpd_action, export_compliance_data
)


# ============================================================================
# PERMISSION HELPERS - Role-based access control
# ============================================================================

def is_cpd_admin(user):
    """Check if user has CPD admin privileges."""
    return (
        user.is_staff or 
        user.acrp_role in ['GLOBAL_SDP', 'PROVIDER_ADMIN', 'INTERNAL_FACILITATOR'] or
        user.groups.filter(name='CPD_Administrators').exists()
    )


def is_cpd_reviewer(user):
    """Check if user can review CPD submissions."""
    return (
        is_cpd_admin(user) or
        user.acrp_role in ['ASSESSOR'] or
        user.groups.filter(name='CPD_Reviewers').exists()
    )


def can_access_user_data(request_user, target_user):
    """Check if user can access another user's CPD data."""
    if request_user == target_user:
        return True
    if is_cpd_admin(request_user):
        return True
    if request_user.manager and request_user.manager == target_user:
        return True
    return False


# ============================================================================
# DASHBOARD VIEWS - Main entry points for different user types
# ============================================================================

@login_required
def dashboard(request):
    """
    Main CPD dashboard - adaptive based on user role.
    Shows different content for admins vs regular users.
    """
    context = {
        'user': request.user,
        'current_period': CPDPeriod.objects.filter(is_current=True).first(),
    }
    
    if is_cpd_admin(request.user):
        return admin_dashboard(request, context)
    else:
        return user_dashboard(request, context)


def admin_dashboard(request, base_context):
    """CPD Admin dashboard with system overview and management tools."""
    
    current_period = base_context['current_period']
    
    # System overview statistics
    stats = {
        'total_users': CPDCompliance.objects.filter(period=current_period).count(),
        'total_activities': CPDActivity.objects.filter(is_active=True).count(),
        'pending_approvals': CPDApproval.objects.filter(
            status__in=[CPDApproval.Status.PENDING, CPDApproval.Status.UNDER_REVIEW]
        ).count(),
        'compliance_rate': 0,
    }
    
    if current_period:
        # Calculate compliance statistics
        compliance_stats = CPDCompliance.objects.filter(
            period=current_period
        ).aggregate(
            compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.COMPLIANT)),
            at_risk=Count('id', filter=Q(compliance_status=CPDCompliance.Status.AT_RISK)),
            non_compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.NON_COMPLIANT)),
            total=Count('id')
        )
        
        if compliance_stats['total'] > 0:
            stats['compliance_rate'] = round(
                (compliance_stats['compliant'] / compliance_stats['total']) * 100, 1
            )
        
        stats.update(compliance_stats)
    
    # Recent activity overview
    recent_activities = CPDActivity.objects.filter(
        created_at__gte=now() - timedelta(days=30),
        is_active=True
    ).order_by('-created_at')[:5]
    
    # Pending approvals requiring attention
    urgent_approvals = CPDApproval.objects.filter(
        status=CPDApproval.Status.PENDING,
        priority__in=[CPDApproval.Priority.HIGH, CPDApproval.Priority.URGENT]
    ).select_related('record__user', 'record__activity').order_by('submitted_at')[:10]
    
    # System health indicators
    health_indicators = {
        'overdue_reviews': CPDApproval.objects.filter(
            status=CPDApproval.Status.PENDING,
            submitted_at__lt=now() - timedelta(days=7)
        ).count(),
        'categories_without_activities': CPDCategory.objects.filter(
            is_active=True,
            activities__isnull=True
        ).count(),
        'inactive_providers': CPDProvider.objects.filter(
            is_active=False
        ).count(),
    }
    
    context = {
        **base_context,
        'is_admin': True,
        'stats': stats,
        'recent_activities': recent_activities,
        'urgent_approvals': urgent_approvals,
        'health_indicators': health_indicators,
    }
    
    return render(request, 'cpd/admin_dashboard.html', context)


def user_dashboard(request, base_context):
    """User/Student dashboard with personal CPD tracking."""
    
    user = request.user
    current_period = base_context['current_period']
    
    # Get user's compliance status for current period
    compliance = None
    if current_period:
        try:
            # Get user's requirement based on their council and level
            requirement = CPDRequirement.objects.filter(
                council=getattr(user, 'council', 'ALL'),
                user_level=getattr(user, 'user_level', 'LEARNER'),
                is_active=True,
                effective_date__lte=now().date()
            ).order_by('-effective_date').first()
            
            if requirement:
                compliance, created = CPDCompliance.objects.get_or_create(
                    user=user,
                    period=current_period,
                    requirement=requirement
                )
                if created or not compliance.calculated_at or \
                   compliance.calculated_at < now() - timedelta(hours=1):
                    compliance.recalculate_compliance()
        except Exception as e:
            # Log error but don't break dashboard
            messages.warning(request, "Unable to calculate compliance status.")
    
    # User's recent CPD activities
    recent_records = CPDRecord.objects.filter(
        user=user,
        period=current_period
    ).select_related(
        'activity__provider', 'activity__category', 'approval'
    ).order_by('-created_at')[:5]
    
    # Upcoming registered activities
    upcoming_activities = CPDRecord.objects.filter(
        user=user,
        status=CPDRecord.Status.REGISTERED,
        activity__start_date__gt=now()
    ).select_related('activity').order_by('activity__start_date')[:5]
    
    # Available activities for registration
    available_activities = CPDActivity.objects.filter(
        approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED,
        is_active=True,
        start_date__gt=now(),
        registration_required=True
    ).exclude(
        records__user=user,
        records__status__in=[CPDRecord.Status.REGISTERED, CPDRecord.Status.COMPLETED]
    ).order_by('start_date')[:5]
    
    # Progress indicators
    progress_data = {
        'points_progress': 0,
        'hours_progress': 0,
        'category_progress': {},
    }
    
    if compliance:
        progress_data['points_progress'] = min(100, compliance.points_progress_percentage)
        progress_data['hours_progress'] = min(100, compliance.hours_progress_percentage)
        
        # Category breakdown
        for cat_id, data in compliance.category_breakdown.items():
            try:
                category = CPDCategory.objects.get(id=cat_id)
                progress_data['category_progress'][category.name] = {
                    'points': data.get('points', 0),
                    'hours': data.get('hours', 0),
                }
            except CPDCategory.DoesNotExist:
                pass
    
    # Action items - things user needs to do
    action_items = []
    
    # Check for activities needing feedback
    needs_feedback = CPDRecord.objects.filter(
        user=user,
        status=CPDRecord.Status.COMPLETED,
        user_rating__isnull=True,
        completion_date__gte=now().date() - timedelta(days=30)
    ).count()
    
    if needs_feedback > 0:
        action_items.append({
            'type': 'feedback',
            'message': f'You have {needs_feedback} completed activities awaiting feedback',
            'url': reverse('cpd:my_records') + '?needs_feedback=true',
            'priority': 'medium'
        })
    
    # Check for pending evidence uploads
    needs_evidence = CPDRecord.objects.filter(
        user=user,
        approval__status=CPDApproval.Status.NEEDS_MORE_INFO,
        evidence_files__isnull=True
    ).count()
    
    if needs_evidence > 0:
        action_items.append({
            'type': 'evidence',
            'message': f'{needs_evidence} activities need additional evidence',
            'url': reverse('cpd:my_records') + '?needs_evidence=true',
            'priority': 'high'
        })
    
    # Check compliance deadline
    if current_period and current_period.days_until_deadline <= 30:
        if compliance and compliance.compliance_status != CPDCompliance.Status.COMPLIANT:
            action_items.append({
                'type': 'deadline',
                'message': f'CPD deadline in {current_period.days_until_deadline} days',
                'url': reverse('cpd:activity_search'),
                'priority': 'urgent'
            })
    
    context = {
        **base_context,
        'is_admin': False,
        'compliance': compliance,
        'recent_records': recent_records,
        'upcoming_activities': upcoming_activities,
        'available_activities': available_activities,
        'progress_data': progress_data,
        'action_items': action_items,
    }
    
    return render(request, 'cpd/user_dashboard.html', context)


# ============================================================================
# ACTIVITY VIEWS - Browsing, searching, and managing activities
# ============================================================================

class ActivityListView(LoginRequiredMixin, ListView):
    """
    Activity browse/search view with advanced filtering.
    Shows different activities based on user permissions.
    """
    model = CPDActivity
    template_name = 'cpd/activity_list.html'
    context_object_name = 'activities'
    paginate_by = 12
    
    def get_queryset(self):
        queryset = CPDActivity.objects.filter(is_active=True).select_related(
            'provider', 'category'
        ).prefetch_related('records')
        
        # Filter based on user permissions
        if not is_cpd_admin(self.request.user):
            queryset = queryset.filter(
                Q(approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED) |
                Q(created_by=self.request.user)
            )
        
        # Apply search filters
        form = CPDActivitySearchForm(
            self.request.GET or None, 
            user=self.request.user
        )
        
        if form.is_valid():
            search = form.cleaned_data.get('search')
            if search:
                queryset = queryset.filter(
                    Q(title__icontains=search) |
                    Q(description__icontains=search) |
                    Q(provider__name__icontains=search)
                )
            
            category = form.cleaned_data.get('category')
            if category:
                queryset = queryset.filter(category=category)
            
            provider = form.cleaned_data.get('provider')
            if provider:
                queryset = queryset.filter(provider=provider)
            
            activity_type = form.cleaned_data.get('activity_type')
            if activity_type:
                queryset = queryset.filter(activity_type=activity_type)
            
            approval_status = form.cleaned_data.get('approval_status')
            if approval_status:
                queryset = queryset.filter(approval_status=approval_status)
            
            date_from = form.cleaned_data.get('date_from')
            if date_from:
                queryset = queryset.filter(start_date__gte=date_from)
            
            date_to = form.cleaned_data.get('date_to')
            if date_to:
                queryset = queryset.filter(start_date__lte=date_to)
            
            is_online = form.cleaned_data.get('is_online')
            if is_online == 'true':
                queryset = queryset.filter(is_online=True)
            elif is_online == 'false':
                queryset = queryset.filter(is_online=False)
            
            registration_open = form.cleaned_data.get('registration_open')
            if registration_open:
                queryset = queryset.filter(
                    registration_required=True,
                    registration_deadline__gte=now()
                )
        
        return queryset.order_by('-start_date', 'title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = CPDActivitySearchForm(
            self.request.GET or None,
            user=self.request.user
        )
        context['total_activities'] = self.get_queryset().count()
        
        # Add filter summaries for UX
        active_filters = []
        if self.request.GET:
            form = context['search_form']
            if form.is_valid():
                for field, value in form.cleaned_data.items():
                    if value:
                        active_filters.append({
                            'field': field,
                            'value': str(value),
                            'display': form.fields[field].label
                        })
        context['active_filters'] = active_filters
        
        return context


class ActivityDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view of a CPD activity with registration/participation options.
    """
    model = CPDActivity
    template_name = 'cpd/activity_detail.html'
    context_object_name = 'activity'
    
    def get_queryset(self):
        queryset = CPDActivity.objects.select_related(
            'provider', 'category', 'created_by'
        ).prefetch_related('records__user')
        
        # Filter based on permissions
        if not is_cpd_admin(self.request.user):
            queryset = queryset.filter(
                Q(approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED) |
                Q(created_by=self.request.user),
                is_active=True
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activity = self.object
        user = self.request.user
        
        # Check user's registration status
        user_record = None
        if user.is_authenticated:
            try:
                user_record = CPDRecord.objects.get(
                    user=user,
                    activity=activity
                )
            except CPDRecord.DoesNotExist:
                pass
        
        context['user_record'] = user_record
        context['can_register'] = (
            activity.is_registration_open and
            not user_record and
            activity.available_spots != 0
        )
        
        # Activity statistics for admins
        if is_cpd_admin(user):
            context['activity_stats'] = {
                'total_registered': activity.records.filter(
                    status__in=[CPDRecord.Status.REGISTERED, CPDRecord.Status.COMPLETED]
                ).count(),
                'completed': activity.records.filter(
                    status=CPDRecord.Status.COMPLETED
                ).count(),
                'average_rating': activity.records.filter(
                    user_rating__isnull=False
                ).aggregate(avg_rating=Avg('user_rating'))['avg_rating'],
            }
        
        # Similar activities
        context['similar_activities'] = CPDActivity.objects.filter(
            category=activity.category,
            is_active=True,
            approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED
        ).exclude(pk=activity.pk).order_by('-start_date')[:3]
        
        # Registration form if applicable
        if context['can_register']:
            context['registration_form'] = QuickRegistrationForm(
                initial={'activity': activity}
            )
        
        return context


@method_decorator(login_required, name='dispatch')
class ActivityCreateView(UserPassesTestMixin, CreateView):
    """Create new CPD activity - different forms for admins vs users."""
    
    template_name = 'cpd/activity_form.html'
    
    def test_func(self):
        return is_cpd_admin(self.request.user) or self.request.user.is_authenticated
    
    def get_form_class(self):
        if is_cpd_admin(self.request.user):
            return CPDActivityForm
        else:
            return UserCPDActivityForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        # Set default approval status based on user role
        if not is_cpd_admin(self.request.user):
            form.instance.approval_status = CPDActivity.ApprovalStatus.REQUIRES_APPROVAL
        
        response = super().form_valid(form)
        
        # Log action
        log_cpd_action(
            user=self.request.user,
            action='CREATE',
            content_object=self.object,
            notes=f"Created activity: {self.object.title}"
        )
        
        messages.success(
            self.request,
            f"Activity '{self.object.title}' created successfully."
        )
        
        return response
    
    def get_success_url(self):
        return reverse('cpd:activity_detail', kwargs={'pk': self.object.pk})


# ============================================================================
# USER PARTICIPATION VIEWS - Registration and record management
# ============================================================================

@login_required
@require_POST
def quick_register(request):
    """Quick registration for pre-approved activities."""
    
    form = QuickRegistrationForm(request.POST)
    
    if form.is_valid():
        activity = form.cleaned_data['activity']
        notes = form.cleaned_data.get('notes', '')
        
        # Check if user can register
        if not activity.is_registration_open:
            messages.error(request, "Registration is closed for this activity.")
            return redirect('cpd:activity_detail', pk=activity.pk)
        
        if activity.available_spots == 0:
            messages.error(request, "This activity is fully booked.")
            return redirect('cpd:activity_detail', pk=activity.pk)
        
        # Check if already registered
        if CPDRecord.objects.filter(user=request.user, activity=activity).exists():
            messages.warning(request, "You are already registered for this activity.")
            return redirect('cpd:activity_detail', pk=activity.pk)
        
        # Create record
        current_period = CPDPeriod.objects.filter(is_current=True).first()
        if not current_period:
            messages.error(request, "No active CPD period found.")
            return redirect('cpd:activity_detail', pk=activity.pk)
        
        record = CPDRecord.objects.create(
            user=request.user,
            activity=activity,
            period=current_period,
            status=CPDRecord.Status.REGISTERED,
            notes=notes
        )
        
        # Create approval record
        CPDApproval.objects.create(
            record=record,
            status=CPDApproval.Status.PENDING,
            original_points=activity.calculate_points()
        )
        
        messages.success(
            request,
            f"Successfully registered for '{activity.title}'. "
            f"You will receive confirmation details via email."
        )
        
        # Send confirmation email (implement in utils)
        # send_registration_confirmation(request.user, activity)
        
    else:
        messages.error(request, "Registration failed. Please try again.")
    
    return redirect('cpd:activity_detail', pk=form.cleaned_data['activity'].pk)


@login_required
def my_records(request):
    """User's personal CPD records dashboard with filtering."""
    
    # Get filter form
    filter_form = CPDRecordFilterForm(request.GET or None)
    
    # Base queryset
    records = CPDRecord.objects.filter(
        user=request.user
    ).select_related(
        'activity__provider', 'activity__category', 'period', 'approval'
    ).prefetch_related('evidence_files').order_by('-created_at')
    
    # Apply filters
    if filter_form.is_valid():
        period = filter_form.cleaned_data.get('period')
        if period:
            records = records.filter(period=period)
        
        status = filter_form.cleaned_data.get('status')
        if status:
            records = records.filter(status=status)
        
        category = filter_form.cleaned_data.get('category')
        if category:
            records = records.filter(activity__category=category)
        
        approval_status = filter_form.cleaned_data.get('approval_status')
        if approval_status:
            records = records.filter(approval__status=approval_status)
        
        points_min = filter_form.cleaned_data.get('points_min')
        if points_min:
            records = records.filter(points_awarded__gte=points_min)
        
        points_max = filter_form.cleaned_data.get('points_max')
        if points_max:
            records = records.filter(points_awarded__lte=points_max)
    
    # Handle special filters from URL parameters
    needs_feedback = request.GET.get('needs_feedback')
    if needs_feedback:
        records = records.filter(
            status=CPDRecord.Status.COMPLETED,
            user_rating__isnull=True
        )
    
    needs_evidence = request.GET.get('needs_evidence')
    if needs_evidence:
        records = records.filter(
            approval__status=CPDApproval.Status.NEEDS_MORE_INFO
        )
    
    # Pagination
    paginator = Paginator(records, 10)
    page_number = request.GET.get('page')
    records_page = paginator.get_page(page_number)
    
    # Summary statistics
    summary = {
        'total_records': records.count(),
        'total_points': records.aggregate(
            total=Coalesce(Sum('points_awarded'), Value(0))
        )['total'],
        'completed_activities': records.filter(
            status=CPDRecord.Status.COMPLETED
        ).count(),
        'pending_approval': records.filter(
            approval__status__in=[
                CPDApproval.Status.PENDING,
                CPDApproval.Status.UNDER_REVIEW
            ]
        ).count(),
    }
    
    context = {
        'records': records_page,
        'filter_form': filter_form,
        'summary': summary,
        'needs_feedback': needs_feedback,
        'needs_evidence': needs_evidence,
    }
    
    return render(request, 'cpd/my_records.html', context)


@login_required
def record_detail(request, pk):
    """Detailed view of a CPD record with evidence and feedback options."""
    
    record = get_object_or_404(
        CPDRecord.objects.select_related(
            'activity__provider', 'activity__category', 'approval', 'period'
        ).prefetch_related('evidence_files'),
        pk=pk
    )
    
    # Permission check
    if not can_access_user_data(request.user, record.user):
        raise Http404("Record not found")
    
    # Handle form submissions
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'evidence':
            evidence_form = CPDEvidenceForm(request.POST, request.FILES)
            if evidence_form.is_valid():
                evidence = evidence_form.save(commit=False)
                evidence.record = record
                evidence.save()
                
                messages.success(request, "Evidence uploaded successfully.")
                return redirect('cpd:record_detail', pk=pk)
        
        elif form_type == 'feedback' and record.user == request.user:
            feedback_form = QuickFeedbackForm(request.POST, instance=record)
            if feedback_form.is_valid():
                feedback_form.save()
                
                # Update activity average rating
                avg_rating = CPDRecord.objects.filter(
                    activity=record.activity,
                    user_rating__isnull=False
                ).aggregate(avg=Avg('user_rating'))['avg']
                
                if avg_rating:
                    record.activity.average_rating = round(avg_rating, 2)
                    record.activity.total_ratings = CPDRecord.objects.filter(
                        activity=record.activity,
                        user_rating__isnull=False
                    ).count()
                    record.activity.save(update_fields=['average_rating', 'total_ratings'])
                
                messages.success(request, "Feedback submitted successfully.")
                return redirect('cpd:record_detail', pk=pk)
    
    # Initialize forms
    evidence_form = CPDEvidenceForm()
    feedback_form = None
    
    if record.user == request.user and record.status == CPDRecord.Status.COMPLETED:
        feedback_form = QuickFeedbackForm(instance=record)
    
    context = {
        'record': record,
        'evidence_form': evidence_form,
        'feedback_form': feedback_form,
        'can_edit': record.user == request.user,
        'can_approve': is_cpd_reviewer(request.user),
    }
    
    return render(request, 'cpd/record_detail.html', context)


# ============================================================================
# APPROVAL WORKFLOW VIEWS - For admin review and processing
# ============================================================================

@user_passes_test(is_cpd_reviewer)
def approval_queue(request):
    """Admin view for managing CPD approval queue."""
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'pending')
    priority_filter = request.GET.get('priority', 'all')
    category_filter = request.GET.get('category', 'all')
    
    # Base queryset
    approvals = CPDApproval.objects.select_related(
        'record__user', 'record__activity__provider', 
        'record__activity__category', 'reviewer'
    ).order_by('priority', 'submitted_at')
    
    # Apply filters
    if status_filter != 'all':
        if status_filter == 'pending':
            approvals = approvals.filter(
                status__in=[CPDApproval.Status.PENDING, CPDApproval.Status.UNDER_REVIEW]
            )
        else:
            approvals = approvals.filter(status=status_filter)
    
    if priority_filter != 'all':
        approvals = approvals.filter(priority=priority_filter)
    
    if category_filter != 'all':
        try:
            category = CPDCategory.objects.get(pk=category_filter)
            approvals = approvals.filter(record__activity__category=category)
        except (CPDCategory.DoesNotExist, ValueError):
            pass
    
    # Pagination
    paginator = Paginator(approvals, 20)
    page_number = request.GET.get('page')
    approvals_page = paginator.get_page(page_number)
    
    # Summary statistics
    stats = {
        'pending_count': CPDApproval.objects.filter(
            status__in=[CPDApproval.Status.PENDING, CPDApproval.Status.UNDER_REVIEW]
        ).count(),
        'urgent_count': CPDApproval.objects.filter(
            status=CPDApproval.Status.PENDING,
            priority=CPDApproval.Priority.URGENT
        ).count(),
        'overdue_count': CPDApproval.objects.filter(
            status=CPDApproval.Status.PENDING,
            submitted_at__lt=now() - timedelta(days=7)
        ).count(),
    }
    
    # Filter options
    categories = CPDCategory.objects.filter(is_active=True).order_by('name')
    
    context = {
        'approvals': approvals_page,
        'stats': stats,
        'categories': categories,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'category': category_filter,
        },
        'bulk_form': BulkApprovalForm(),
    }
    
    return render(request, 'cpd/approval_queue.html', context)


@user_passes_test(is_cpd_reviewer)
def approval_detail(request, pk):
    """Detailed approval view with decision form."""
    
    approval = get_object_or_404(
        CPDApproval.objects.select_related(
            'record__user', 'record__activity__provider',
            'record__activity__category', 'record__period'
        ).prefetch_related('record__evidence_files'),
        pk=pk
    )
    
    if request.method == 'POST':
        form = CPDApprovalForm(request.POST, instance=approval)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.reviewer = request.user
            approval.reviewed_at = now()
            
            # Update review timing
            if approval.submitted_at:
                delta = approval.reviewed_at - approval.submitted_at
                approval.days_in_review = delta.days
            
            approval.save()
            
            # Send notification to user
            send_approval_notification(approval)
            
            # Log action
            log_cpd_action(
                user=request.user,
                action='APPROVE' if approval.status == CPDApproval.Status.APPROVED else 'REJECT',
                content_object=approval.record,
                notes=f"Approval decision: {approval.get_status_display()}"
            )
            
            # Update user compliance if approved
            if approval.status == CPDApproval.Status.APPROVED:
                try:
                    compliance = CPDCompliance.objects.get(
                        user=approval.record.user,
                        period=approval.record.period
                    )
                    compliance.recalculate_compliance()
                except CPDCompliance.DoesNotExist:
                    pass
            
            messages.success(
                request,
                f"Approval decision recorded: {approval.get_status_display()}"
            )
            
            # Redirect to next pending approval or back to queue
            next_approval = CPDApproval.objects.filter(
                status=CPDApproval.Status.PENDING,
                pk__gt=approval.pk
            ).first()
            
            if next_approval:
                return redirect('cpd:approval_detail', pk=next_approval.pk)
            else:
                return redirect('cpd:approval_queue')
    
    else:
        form = CPDApprovalForm(instance=approval)
    
    # Calculate recommended points based on category and hours
    recommended_points = approval.record.activity.calculate_points()
    
    context = {
        'approval': approval,
        'form': form,
        'recommended_points': recommended_points,
        'evidence_files': approval.record.evidence_files.all(),
    }
    
    return render(request, 'cpd/approval_detail.html', context)


@user_passes_test(is_cpd_reviewer)
@require_POST
def bulk_approval(request):
    """Handle bulk approval operations."""
    
    form = BulkApprovalForm(request.POST)
    
    if form.is_valid():
        action = form.cleaned_data['action']
        record_ids = form.cleaned_data['selected_records']
        bulk_comments = form.cleaned_data['bulk_comments']
        
        # Get approvals to update
        approvals = CPDApproval.objects.filter(id__in=record_ids)
        
        updated_count = 0
        
        for approval in approvals:
            if action == 'approve':
                approval.status = CPDApproval.Status.APPROVED
                approval.reviewer = request.user
                approval.reviewed_at = now()
                if bulk_comments:
                    approval.reviewer_comments = bulk_comments
                
            elif action == 'reject':
                approval.status = CPDApproval.Status.REJECTED
                approval.reviewer = request.user
                approval.reviewed_at = now()
                if bulk_comments:
                    approval.rejection_reason = bulk_comments
                
            elif action == 'priority_high':
                approval.priority = CPDApproval.Priority.HIGH
                
            elif action == 'priority_normal':
                approval.priority = CPDApproval.Priority.NORMAL
            
            approval.save()
            updated_count += 1
            
            # Send notifications for status changes
            if action in ['approve', 'reject']:
                send_approval_notification(approval)
        
        messages.success(
            request,
            f"Bulk operation completed. {updated_count} records updated."
        )
    
    else:
        messages.error(request, "Invalid bulk operation request.")
    
    return redirect('cpd:approval_queue')


# ============================================================================
# REPORTING AND ANALYTICS VIEWS
# ============================================================================

@user_passes_test(is_cpd_admin)
def analytics_dashboard(request):
    """Comprehensive analytics dashboard for CPD administrators."""
    
    # Get time period for analysis
    period_id = request.GET.get('period')
    if period_id:
        try:
            period = CPDPeriod.objects.get(pk=period_id)
        except CPDPeriod.DoesNotExist:
            period = CPDPeriod.objects.filter(is_current=True).first()
    else:
        period = CPDPeriod.objects.filter(is_current=True).first()
    
    if not period:
        messages.warning(request, "No CPD period found for analysis.")
        return redirect('cpd:dashboard')
    
    # Overall compliance statistics
    compliance_stats = CPDCompliance.objects.filter(period=period).aggregate(
        total_users=Count('id'),
        compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.COMPLIANT)),
        at_risk=Count('id', filter=Q(compliance_status=CPDCompliance.Status.AT_RISK)),
        non_compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.NON_COMPLIANT)),
        avg_points=Avg('total_points_earned'),
        avg_hours=Avg('total_hours_completed'),
    )
    
    # Activity statistics
    activity_stats = CPDActivity.objects.filter(
        records__period=period
    ).aggregate(
        total_activities=Count('id', distinct=True),
        avg_participants=Avg('records__count'),
        avg_rating=Avg('average_rating'),
    )
    
    # Category breakdown
    category_stats = CPDCategory.objects.annotate(
        total_records=Count('activities__records', filter=Q(activities__records__period=period)),
        total_points=Sum('activities__records__points_awarded', 
                        filter=Q(activities__records__period=period)),
        avg_rating=Avg('activities__average_rating')
    ).filter(total_records__gt=0).order_by('-total_records')
    
    # Provider performance
    provider_stats = CPDProvider.objects.annotate(
        total_activities=Count('activities', filter=Q(activities__records__period=period)),
        total_participants=Count('activities__records', filter=Q(activities__records__period=period)),
        avg_rating=Avg('activities__average_rating')
    ).filter(total_activities__gt=0).order_by('-total_participants')[:10]
    
    # Timeline data for charts
    timeline_data = []
    start_date = period.start_date
    current_date = start_date
    
    while current_date <= min(period.end_date, now().date()):
        day_records = CPDRecord.objects.filter(
            period=period,
            completion_date=current_date
        ).aggregate(
            count=Count('id'),
            points=Sum('points_awarded')
        )
        
        timeline_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'records': day_records['count'] or 0,
            'points': float(day_records['points'] or 0),
        })
        
        current_date += timedelta(days=1)
    
    # Risk analysis - users falling behind
    at_risk_users = CPDCompliance.objects.filter(
        period=period,
        compliance_status__in=[
            CPDCompliance.Status.AT_RISK,
            CPDCompliance.Status.NON_COMPLIANT
        ]
    ).select_related('user').order_by('points_progress_percentage')[:20]
    
    context = {
        'period': period,
        'all_periods': CPDPeriod.objects.all().order_by('-start_date'),
        'compliance_stats': compliance_stats,
        'activity_stats': activity_stats,
        'category_stats': category_stats,
        'provider_stats': provider_stats,
        'timeline_data': json.dumps(timeline_data),
        'at_risk_users': at_risk_users,
    }
    
    return render(request, 'cpd/analytics_dashboard.html', context)


@user_passes_test(is_cpd_admin)
def generate_report(request):
    """Generate custom compliance reports."""
    
    if request.method == 'POST':
        form = ComplianceReportForm(request.POST)
        if form.is_valid():
            period = form.cleaned_data['period']
            council = form.cleaned_data['council']
            user_level = form.cleaned_data.get('user_level')
            compliance_status = form.cleaned_data.get('compliance_status')
            report_format = form.cleaned_data['report_format']
            include_details = form.cleaned_data['include_details']
            include_evidence = form.cleaned_data['include_evidence']
            
            # Build queryset based on filters
            compliance_records = CPDCompliance.objects.filter(
                period=period
            ).select_related('user', 'requirement')
            
            if council != 'ALL':
                compliance_records = compliance_records.filter(requirement__council=council)
            
            if user_level and user_level != 'ALL':
                compliance_records = compliance_records.filter(requirement__user_level=user_level)
            
            if compliance_status:
                compliance_records = compliance_records.filter(
                    compliance_status__in=compliance_status
                )
            
            # Generate report based on format
            if report_format == 'html':
                context = {
                    'compliance_records': compliance_records,
                    'period': period,
                    'council': council,
                    'user_level': user_level,
                    'include_details': include_details,
                    'include_evidence': include_evidence,
                    'generated_at': now(),
                    'generated_by': request.user,
                }
                return render(request, 'cpd/reports/compliance_report.html', context)
            
            elif report_format == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="cpd_compliance_{period.name}.csv"'
                
                writer = csv.writer(response)
                writer.writerow([
                    'User', 'Email', 'Council', 'User Level', 'Points Required',
                    'Points Earned', 'Hours Required', 'Hours Completed',
                    'Compliance Status', 'Progress %'
                ])
                
                for record in compliance_records:
                    writer.writerow([
                        record.user.get_full_name,
                        record.user.email,
                        record.requirement.get_council_display(),
                        record.requirement.get_user_level_display(),
                        record.requirement.total_points_required,
                        record.total_points_earned,
                        record.requirement.total_hours_required,
                        record.total_hours_completed,
                        record.get_compliance_status_display(),
                        record.points_progress_percentage
                    ])
                
                return response
            
            # Add PDF and Excel generation here
            else:
                messages.info(request, f"{report_format.upper()} export coming soon!")
                return redirect('cpd:generate_report')
    
    else:
        form = ComplianceReportForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'cpd/generate_report.html', context)


# ============================================================================
# CERTIFICATE AND VERIFICATION VIEWS
# ============================================================================

@login_required
def my_certificates(request):
    """User's CPD certificates and compliance records."""
    
    certificates = CPDCertificate.objects.filter(
        user=request.user
    ).select_related('period', 'compliance').order_by('-issue_date')
    
    # Current compliance status
    current_period = CPDPeriod.objects.filter(is_current=True).first()
    current_compliance = None
    
    if current_period:
        try:
            current_compliance = CPDCompliance.objects.get(
                user=request.user,
                period=current_period
            )
        except CPDCompliance.DoesNotExist:
            pass
    
    context = {
        'certificates': certificates,
        'current_period': current_period,
        'current_compliance': current_compliance,
    }
    
    return render(request, 'cpd/my_certificates.html', context)


def verify_certificate(request, token):
    """Public certificate verification view."""
    
    try:
        certificate = CPDCertificate.objects.select_related(
            'user', 'period', 'compliance'
        ).get(verification_token=token, is_valid=True)
    except CPDCertificate.DoesNotExist:
        raise Http404("Certificate not found or invalid")
    
    context = {
        'certificate': certificate,
        'is_public_view': True,
    }
    
    return render(request, 'cpd/certificate_verification.html', context)


@login_required
def download_certificate(request, pk):
    """Download user's certificate as PDF."""
    
    certificate = get_object_or_404(
        CPDCertificate.objects.select_related('user', 'period'),
        pk=pk
    )
    
    # Permission check
    if not (certificate.user == request.user or is_cpd_admin(request.user)):
        return HttpResponseForbidden("Access denied")
    
    # Generate PDF if not exists
    if not certificate.certificate_file:
        pdf_file = generate_compliance_certificate(certificate)
        certificate.certificate_file = pdf_file
        certificate.save()
    
    # Serve file
    response = HttpResponse(
        certificate.certificate_file.read(),
        content_type='application/pdf'
    )
    response['Content-Disposition'] = f'attachment; filename="{certificate.certificate_number}.pdf"'
    
    return response


# ============================================================================
# API VIEWS - For AJAX and external integrations
# ============================================================================

@login_required
def api_activity_search(request):
    """AJAX endpoint for activity search autocomplete."""
    
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    activities = CPDActivity.objects.filter(
        Q(title__icontains=query) | Q(provider__name__icontains=query),
        is_active=True,
        approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED
    ).select_related('provider')[:10]
    
    results = []
    for activity in activities:
        results.append({
            'id': activity.id,
            'title': activity.title,
            'provider': activity.provider.name,
            'category': activity.category.name,
            'points': float(activity.calculate_points()),
            'start_date': activity.start_date.isoformat() if activity.start_date else None,
        })
    
    return JsonResponse({'results': results})


@login_required
def api_user_progress(request):
    """AJAX endpoint for user progress data."""
    
    period_id = request.GET.get('period')
    try:
        period = CPDPeriod.objects.get(pk=period_id) if period_id else CPDPeriod.objects.filter(is_current=True).first()
    except CPDPeriod.DoesNotExist:
        return JsonResponse({'error': 'Period not found'}, status=404)
    
    try:
        compliance = CPDCompliance.objects.get(
            user=request.user,
            period=period
        )
        
        data = {
            'points_progress': float(compliance.points_progress_percentage),
            'hours_progress': float(compliance.hours_progress_percentage),
            'points_earned': float(compliance.total_points_earned),
            'points_required': float(compliance.requirement.total_points_required),
            'hours_completed': float(compliance.total_hours_completed),
            'hours_required': float(compliance.requirement.total_hours_required),
            'status': compliance.compliance_status,
            'category_breakdown': compliance.category_breakdown,
        }
        
        return JsonResponse(data)
        
    except CPDCompliance.DoesNotExist:
        return JsonResponse({'error': 'Compliance record not found'}, status=404)


@user_passes_test(is_cpd_admin)
def api_admin_stats(request):
    """AJAX endpoint for admin dashboard statistics."""
    
    period_id = request.GET.get('period')
    try:
        period = CPDPeriod.objects.get(pk=period_id) if period_id else CPDPeriod.objects.filter(is_current=True).first()
    except CPDPeriod.DoesNotExist:
        return JsonResponse({'error': 'Period not found'}, status=404)
    
    # Calculate statistics
    compliance_stats = CPDCompliance.objects.filter(period=period).aggregate(
        total=Count('id'),
        compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.COMPLIANT)),
        at_risk=Count('id', filter=Q(compliance_status=CPDCompliance.Status.AT_RISK)),
        non_compliant=Count('id', filter=Q(compliance_status=CPDCompliance.Status.NON_COMPLIANT)),
    )
    
    pending_approvals = CPDApproval.objects.filter(
        record__period=period,
        status__in=[CPDApproval.Status.PENDING, CPDApproval.Status.UNDER_REVIEW]
    ).count()
    
    data = {
        'period': period.name,
        'compliance_stats': compliance_stats,
        'pending_approvals': pending_approvals,
        'compliance_rate': round((compliance_stats['compliant'] / max(compliance_stats['total'], 1)) * 100, 1)
    }
    
    return JsonResponse(data)


# ============================================================================
# UTILITY VIEWS - Helper functions and redirects
# ============================================================================

@login_required
def quick_actions(request):
    """Handle quick action requests from dashboard."""
    
    action = request.GET.get('action')
    
    if action == 'register_next_activity':
        # Find next available activity
        next_activity = CPDActivity.objects.filter(
            approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED,
            is_active=True,
            start_date__gt=now(),
            registration_required=True
        ).exclude(
            records__user=request.user
        ).order_by('start_date').first()
        
        if next_activity:
            return redirect('cpd:activity_detail', pk=next_activity.pk)
        else:
            messages.info(request, "No upcoming activities available for registration.")
            return redirect('cpd:activity_search')
    
    elif action == 'submit_external':
        return redirect('cpd:activity_create')
    
    elif action == 'view_progress':
        return redirect('cpd:my_records')
    
    else:
        return redirect('cpd:dashboard')


@login_required
def export_my_data(request):
    """Export user's CPD data as CSV."""
    
    records = CPDRecord.objects.filter(
        user=request.user
    ).select_related(
        'activity__provider', 'activity__category', 'period', 'approval'
    ).order_by('-created_at')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="my_cpd_records_{request.user.username}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Period', 'Activity Title', 'Provider', 'Category', 'Type',
        'Status', 'Registration Date', 'Completion Date', 'Points Claimed',
        'Points Awarded', 'Hours', 'Rating', 'Approval Status'
    ])
    
    for record in records:
        writer.writerow([
            record.period.name,
            record.display_title,
            record.display_provider,
            record.activity.category.name,
            record.activity.get_activity_type_display(),
            record.get_status_display(),
            record.registration_date.strftime('%Y-%m-%d'),
            record.completion_date.strftime('%Y-%m-%d') if record.completion_date else '',
            record.points_claimed,
            record.points_awarded,
            record.final_hours,
            record.user_rating or '',
            record.approval.get_status_display() if hasattr(record, 'approval') else ''
        ])
    
    return response


# ============================================================================
# ERROR HANDLING VIEWS
# ============================================================================

def cpd_404(request, exception):
    """Custom 404 page for CPD app."""
    return render(request, 'cpd/404.html', status=404)


def cpd_403(request, exception):
    """Custom 403 page for CPD app."""
    return render(request, 'cpd/403.html', status=403)


def cpd_500(request):
    """Custom 500 page for CPD app."""
    return render(request, 'cpd/500.html', status=500)