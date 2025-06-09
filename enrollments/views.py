from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.urls import reverse
from django.core.mail import send_mail
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging

from .models import (
    CGMPAffiliation, CPSCAffiliation, CMTPAffiliation, 
    Document, RegistrationSession
)
from .forms import (
    CGMPForm, CPSCForm, CMTPForm, 
    DocumentForm, RegistrationTypeForm
)
from accounts.models import User

# Configure logging
logger = logging.getLogger(__name__)

# Constants for pagination and caching
ITEMS_PER_PAGE = 25
CACHE_TIMEOUT = 900  # 15 minutes
SEARCH_CACHE_TIMEOUT = 300  # 5 minutes


# Security and permission utilities
def is_admin_or_manager(user):
    """Check if user has admin or manager privileges"""
    return user.acrp_role in {
        User.ACRPRole.GLOBAL_SDP,
        User.ACRPRole.PROVIDER_ADMIN,
    }

def can_approve_applications(user):
    """Check if user can approve applications"""
    return user.acrp_role in {
        User.ACRPRole.GLOBAL_SDP,
        User.ACRPRole.PROVIDER_ADMIN
    }

def get_client_ip(request):
    """Safely extract client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

# Rate limiting decorator
def rate_limit(max_requests=10, window=3600):
    """Simple rate limiting decorator"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            cache_key = f"rate_limit:{view_func.__name__}:{ip}"
            
            current_requests = cache.get(cache_key, 0)
            if current_requests >= max_requests:
                logger.warning(f"Rate limit exceeded for IP {ip} on {view_func.__name__}")
                messages.error(request, "Too many requests. Please try again later.")
                return redirect('enrollments:onboarding')
            
            cache.set(cache_key, current_requests + 1, window)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

# Enhanced onboarding view
@csrf_protect
@rate_limit(max_requests=20, window=3600)
def onboarding(request):
    """
    Enhanced onboarding flow for selecting registration type.
    Implements security measures and user experience improvements.
    """
    if request.method == 'POST':
        form = RegistrationTypeForm(request.POST)
        if form.is_valid():
            choice = form.cleaned_data['registration_type']
            
            # Create or update registration session
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            
            # Store registration session with audit trail
            reg_session, created = RegistrationSession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    'registration_type': choice,
                    'user': request.user if request.user.is_authenticated else None,
                    'ip_address': get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500]
                }
            )
            
            if not created:
                reg_session.registration_type = choice
                reg_session.save(update_fields=['registration_type'])
            
            # Route to appropriate council registration
            routing_map = {
                'cgmp': 'enrollments:cgmp_create',
                'cpsc': 'enrollments:cpsc_create', 
                'cmtp': 'enrollments:cmtp_create',
                'student': 'enrollments:learner_apply_prompt',
                'provider': 'providers:provider_self_register'
            }
            
            redirect_url = routing_map.get(choice)
            if redirect_url:
                logger.info(f"Registration initiated: {choice} from IP {get_client_ip(request)}")
                return redirect(redirect_url)
        
        messages.error(request, "Please select a valid registration option.")
    else:
        form = RegistrationTypeForm()
    
    return render(request, 'enrollments/onboarding.html', {'form': form})



def learner_apply_prompt(request):
    """
    Simple form asking the applicant to paste their application link token,
    then redirecting them to the real student apply page.
    """
    if request.method == 'POST':
        token = request.POST.get('token','').strip()
        if token:
            return redirect(reverse('student:learner_apply', args=[token]))
        messages.error(request, "Please enter your registration link token.")
    return render(request, 'enrollments/learner_apply_prompt.html')

# Only GLOBAL_SDP or PROVIDER_ADMIN may approve :contentReference[oaicite:5]{index=5}
def is_admin(user):
    return user.acrp_role in {
        User.ACRPRole.GLOBAL_SDP,
        User.ACRPRole.PROVIDER_ADMIN
    }



# Generic optimized list view with advanced filtering
def _enhanced_list_view(request, model, template, search_fields, permission_required_perm=None):
    """
    Enhanced generic list view with pagination, search, filtering, and caching
    """
    if permission_required_perm and not request.user.has_perm(permission_required_perm):
        return HttpResponseForbidden("Insufficient permissions")
    
    # Build cache key for query optimization
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    page_num = request.GET.get('page', 1)
    
    cache_key = f"list_view:{model.__name__}:{search_query}:{status_filter}:{page_num}"
    
    # Try to get from cache first
    cached_result = cache.get(cache_key)
    if cached_result and not settings.DEBUG:
        return render(request, template, cached_result)
    
    # Build optimized queryset
    queryset = model.objects.select_related('created_user', 'approved_by')
    
    # Apply search filters
    if search_query:
        search_q = Q()
        for field in search_fields:
            search_q |= Q(**{f"{field}__icontains": search_query})
        queryset = queryset.filter(search_q)
    
    # Apply status filters
    if status_filter == 'approved':
        queryset = queryset.filter(approved=True)
    elif status_filter == 'pending':
        queryset = queryset.filter(approved=False)
    
    # Order by creation date (newest first)
    queryset = queryset.order_by('-created_at')
    
    # Implement pagination
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    try:
        applications = paginator.page(page_num)
    except PageNotAnInteger:
        applications = paginator.page(1)
    except EmptyPage:
        applications = paginator.page(paginator.num_pages)
    
    # Prepare context
    context = {
        'applications': applications,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_count': queryset.count(),
        'model_name': model.__name__.lower().replace('affiliation', '')
    }
    
    # Cache the result
    cache.set(cache_key, context, SEARCH_CACHE_TIMEOUT)
    
    return render(request, template, context)




# Generic list view with search
def _list(request, model, template, search_fields):
    qs = model.objects.all()
    q  = request.GET.get('search', '').strip()
    if q:
        query = Q()
        for f in search_fields:
            query |= Q(**{f+"__icontains": q})
        qs = qs.filter(query)
    return render(request, template, {'objects': qs, 'search_query': q})


# CGMP Views
@login_required
@permission_required('enrollments.view_cgmpaffiliation', raise_exception=True)
def cgmp_list(request):
    """List all CGMP affiliations with search and filtering"""
    return _enhanced_list_view(
        request, 
        CGMPAffiliation, 
        'enrollments/cgmp_list.html',
        ['first_name', 'last_name', 'surname', 'email', 'current_ministry_role'],
        'enrollments.view_cgmpaffiliation'
    )

@csrf_protect
@rate_limit(max_requests=5, window=3600)
@transaction.atomic
def cgmp_create(request):
    """
    Create new CGMP affiliation with enhanced security and validation
    """
    if request.method == 'POST':
        form = CGMPForm(request.POST, request=request)
        
        if form.is_valid():
            try:
                # Save the affiliation
                cgmp = form.save(commit=False)
                if request.user.is_authenticated:
                    cgmp.created_user = request.user
                cgmp.save()
                
                # Log successful creation
                logger.info(f"CGMP application created: ID {cgmp.id}, Email {cgmp.email}")
                
                # Clear relevant caches
                cache.delete_many([
                    f"list_view:CGMPAffiliation:*",
                    f"stats:cgmp:*"
                ])
                
                # Success message and redirect
                messages.success(request, "Your CGMP application has been submitted successfully!")
                return render(request, 'enrollments/application_success.html', {
                    'application': cgmp,
                    'council_type': 'CGMP'
                })
                
            except Exception as e:
                logger.error(f"Error creating CGMP application: {str(e)}")
                messages.error(request, "An error occurred. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CGMPForm()
    
    return render(request, 'enrollments/cgmp_form.html', {'form': form})

@login_required
@permission_required('enrollments.change_cgmpaffiliation', raise_exception=True)
@transaction.atomic  
def cgmp_update(request, pk):
    """Update existing CGMP affiliation"""
    cgmp = get_object_or_404(CGMPAffiliation, pk=pk)
    
    if request.method == 'POST':
        form = CGMPForm(request.POST, instance=cgmp, request=request)
        if form.is_valid():
            form.save()
            logger.info(f"CGMP application updated: ID {pk}")
            messages.success(request, "CGMP application updated successfully.")
            return redirect('enrollments:cgmp_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CGMPForm(instance=cgmp)
    
    return render(request, 'enrollments/cgmp_form.html', {
        'form': form, 
        'object': cgmp,
        'is_update': True
    })

@login_required
@permission_required('enrollments.view_cgmpaffiliation', raise_exception=True)
def cgmp_detail(request, pk):
    """View CGMP affiliation details"""
    cgmp = get_object_or_404(
        CGMPAffiliation.objects.select_related('created_user', 'approved_by')
        .prefetch_related('documents'), 
        pk=pk
    )
    
    return render(request, 'enrollments/cgmp_detail.html', {'object': cgmp})

@login_required
@permission_required('enrollments.delete_cgmpaffiliation', raise_exception=True)
@require_http_methods(["GET", "POST"])
def cgmp_delete(request, pk):
    """Delete CGMP affiliation with confirmation"""
    cgmp = get_object_or_404(CGMPAffiliation, pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            cgmp.delete()
            logger.info(f"CGMP application deleted: ID {pk}")
            messages.success(request, "CGMP application deleted successfully.")
            return redirect('enrollments:cgmp_list')
    
    return render(request, 'enrollments/confirm_delete.html', {
        'object': cgmp,
        'object_type': 'CGMP Application'
    })

# CPSC Views (similar pattern)
@login_required
@permission_required('enrollments.view_cpscaffiliation', raise_exception=True)
def cpsc_list(request):
    """List all CPSC affiliations"""
    return _enhanced_list_view(
        request,
        CPSCAffiliation,
        'enrollments/cpsc_list.html', 
        ['first_name', 'last_name', 'surname', 'email', 'counseling_certification'],
        'enrollments.view_cpscaffiliation'
    )

@csrf_protect
@rate_limit(max_requests=5, window=3600)
@transaction.atomic
def cpsc_create(request):
    """Create new CPSC affiliation"""
    if request.method == 'POST':
        form = CPSCForm(request.POST, request=request)
        
        if form.is_valid():
            try:
                cpsc = form.save(commit=False)
                if request.user.is_authenticated:
                    cpsc.created_user = request.user
                cpsc.save()
                
                logger.info(f"CPSC application created: ID {cpsc.id}, Email {cpsc.email}")
                messages.success(request, "Your CPSC application has been submitted successfully!")
                
                return render(request, 'enrollments/application_success.html', {
                    'application': cpsc,
                    'council_type': 'CPSC'
                })
                
            except Exception as e:
                logger.error(f"Error creating CPSC application: {str(e)}")
                messages.error(request, "An error occurred. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CPSCForm()
    
    return render(request, 'enrollments/cpsc_form.html', {'form': form})

# CMTP Views (similar pattern)
@login_required  
@permission_required('enrollments.view_cmtpaffiliation', raise_exception=True)
def cmtp_list(request):
    """List all CMTP affiliations"""
    return _enhanced_list_view(
        request,
        CMTPAffiliation,
        'enrollments/cmtp_list.html',
        ['first_name', 'last_name', 'surname', 'email', 'institution_name'],
        'enrollments.view_cmtpaffiliation'
    )

@csrf_protect
@rate_limit(max_requests=5, window=3600)
@transaction.atomic
def cmtp_create(request):
    """Create new CMTP affiliation"""
    if request.method == 'POST':
        form = CMTPForm(request.POST, request=request)
        
        if form.is_valid():
            try:
                cmtp = form.save(commit=False)
                if request.user.is_authenticated:
                    cmtp.created_user = request.user
                cmtp.save()
                
                logger.info(f"CMTP application created: ID {cmtp.id}, Email {cmtp.email}")
                messages.success(request, "Your CMTP application has been submitted successfully!")
                
                return render(request, 'enrollments/application_success.html', {
                    'application': cmtp,
                    'council_type': 'CMTP'  
                })
                
            except Exception as e:
                logger.error(f"Error creating CMTP application: {str(e)}")
                messages.error(request, "An error occurred. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CMTPForm()
    
    return render(request, 'enrollments/cmtp_form.html', {'form': form})



# Universal approval/rejection views
@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
@transaction.atomic
def approve_application(request, model_type, pk):
    """
    Universal application approval handler for all council types
    """
    model_map = {
        'cgmp': CGMPAffiliation,
        'cpsc': CPSCAffiliation, 
        'cmtp': CMTPAffiliation
    }
    
    model = model_map.get(model_type)
    if not model:
        raise Http404("Invalid application type")
    
    application = get_object_or_404(model, pk=pk)
    
    # Prevent double approval
    if application.approved:
        messages.warning(request, "Application is already approved.")
        return redirect(f'enrollments:{model_type}_list')
    
    try:
        # Update approval fields
        application.approved = True
        application.approved_by = request.user
        application.approved_at = timezone.now()
        application.save(update_fields=['approved', 'approved_by', 'approved_at'])
        
        # Log the approval
        logger.info(f"{model_type.upper()} application approved: ID {pk} by user {request.user.id}")
        
        # Send approval email (implement as needed)
        # send_approval_email(application)
        
        messages.success(request, f"{model_type.upper()} application approved successfully.")
        
    except Exception as e:
        logger.error(f"Error approving {model_type} application {pk}: {str(e)}")
        messages.error(request, "An error occurred during approval.")
    
    return redirect(f'enrollments:{model_type}_list')

@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None) 
@require_http_methods(["GET", "POST"])
@transaction.atomic
def reject_application(request, model_type, pk):
    """
    Universal application rejection handler
    """
    model_map = {
        'cgmp': CGMPAffiliation,
        'cpsc': CPSCAffiliation,
        'cmtp': CMTPAffiliation
    }
    
    model = model_map.get(model_type)
    if not model:
        raise Http404("Invalid application type")
    
    application = get_object_or_404(model, pk=pk)
    
    if request.method == 'POST':
        try:
            # Mark as rejected
            application.approved = False
            application.save(update_fields=['approved'])
            
            # Log the rejection  
            logger.info(f"{model_type.upper()} application rejected: ID {pk} by user {request.user.id}")
            
            # Send rejection email (implement as needed)
            # send_rejection_email(application)
            
            messages.success(request, f"{model_type.upper()} application rejected and notification sent.")
            
        except Exception as e:
            logger.error(f"Error rejecting {model_type} application {pk}: {str(e)}")
            messages.error(request, "An error occurred during rejection.")
        
        return redirect(f'enrollments:{model_type}_list')
    
    return render(request, 'enrollments/confirm_reject.html', {
        'object': application,
        'model_type': model_type.upper()
    })

# Dashboard view for statistics
@login_required
@user_passes_test(is_admin_or_manager, login_url='/', redirect_field_name=None)
@cache_page(CACHE_TIMEOUT)
def enrollment_dashboard(request):
    """
    Administrative dashboard with enrollment statistics and metrics
    """
    stats = {
        'cgmp': {
            'total': CGMPAffiliation.objects.count(),
            'approved': CGMPAffiliation.objects.filter(approved=True).count(),
            'pending': CGMPAffiliation.objects.filter(approved=False).count(),
        },
        'cpsc': {
            'total': CPSCAffiliation.objects.count(), 
            'approved': CPSCAffiliation.objects.filter(approved=True).count(),
            'pending': CPSCAffiliation.objects.filter(approved=False).count(),
        },
        'cmtp': {
            'total': CMTPAffiliation.objects.count(),
            'approved': CMTPAffiliation.objects.filter(approved=True).count(), 
            'pending': CMTPAffiliation.objects.filter(approved=False).count(),
        }
    }
    
    # Recent applications
    recent_applications = []
    
    for model, name in [(CGMPAffiliation, 'CGMP'), (CPSCAffiliation, 'CPSC'), (CMTPAffiliation, 'CMTP')]:
        recent = model.objects.select_related('created_user').order_by('-created_at')[:5]
        for app in recent:
            recent_applications.append({
                'type': name,
                'name': app.get_display_name(),
                'email': app.email,
                'created_at': app.created_at,
                'approved': app.approved
            })
    
    # Sort by creation date
    recent_applications.sort(key=lambda x: x['created_at'], reverse=True)
    recent_applications = recent_applications[:10]  # Top 10 most recent
    
    return render(request, 'enrollments/dashboard.html', {
        'stats': stats,
        'recent_applications': recent_applications
    })

# CPSC CRUD Operations
@login_required
@permission_required('enrollments.change_cpscaffiliation', raise_exception=True)
@transaction.atomic
def cpsc_update(request, pk):
    """Update existing CPSC affiliation"""
    cpsc = get_object_or_404(CPSCAffiliation, pk=pk)
    
    if request.method == 'POST':
        form = CPSCForm(request.POST, instance=cpsc, request=request)
        if form.is_valid():
            form.save()
            logger.info(f"CPSC application updated: ID {pk}")
            messages.success(request, "CPSC application updated successfully.")
            return redirect('enrollments:cpsc_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CPSCForm(instance=cpsc)
    
    return render(request, 'enrollments/cpsc_form.html', {
        'form': form,
        'object': cpsc,
        'is_update': True
    })

@login_required
@permission_required('enrollments.view_cpscaffiliation', raise_exception=True)
def cpsc_detail(request, pk):
    """View CPSC affiliation details"""
    cpsc = get_object_or_404(
        CPSCAffiliation.objects.select_related('created_user', 'approved_by')
        .prefetch_related('documents'),
        pk=pk
    )
    return render(request, 'enrollments/cpsc_detail.html', {'object': cpsc})

@login_required
@permission_required('enrollments.delete_cpscaffiliation', raise_exception=True)
@require_http_methods(["GET", "POST"])
def cpsc_delete(request, pk):
    """Delete CPSC affiliation with confirmation"""
    cpsc = get_object_or_404(CPSCAffiliation, pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            cpsc.delete()
            logger.info(f"CPSC application deleted: ID {pk}")
            messages.success(request, "CPSC application deleted successfully.")
            return redirect('enrollments:cpsc_list')
    
    return render(request, 'enrollments/confirm_delete.html', {
        'object': cpsc,
        'object_type': 'CPSC Application'
    })

# CMTP CRUD Operations
@login_required
@permission_required('enrollments.change_cmtpaffiliation', raise_exception=True)
@transaction.atomic
def cmtp_update(request, pk):
    """Update existing CMTP affiliation"""
    cmtp = get_object_or_404(CMTPAffiliation, pk=pk)
    
    if request.method == 'POST':
        form = CMTPForm(request.POST, instance=cmtp, request=request)
        if form.is_valid():
            form.save()
            logger.info(f"CMTP application updated: ID {pk}")
            messages.success(request, "CMTP application updated successfully.")
            return redirect('enrollments:cmtp_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CMTPForm(instance=cmtp)
    
    return render(request, 'enrollments/cmtp_form.html', {
        'form': form,
        'object': cmtp,
        'is_update': True
    })

@login_required
@permission_required('enrollments.view_cmtpaffiliation', raise_exception=True)
def cmtp_detail(request, pk):
    """View CMTP affiliation details"""
    cmtp = get_object_or_404(
        CMTPAffiliation.objects.select_related('created_user', 'approved_by')
        .prefetch_related('documents'),
        pk=pk
    )
    return render(request, 'enrollments/cmtp_detail.html', {'object': cmtp})

@login_required
@permission_required('enrollments.delete_cmtpaffiliation', raise_exception=True)
@require_http_methods(["GET", "POST"])
def cmtp_delete(request, pk):
    """Delete CMTP affiliation with confirmation"""
    cmtp = get_object_or_404(CMTPAffiliation, pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            cmtp.delete()
            logger.info(f"CMTP application deleted: ID {pk}")
            messages.success(request, "CMTP application deleted successfully.")
            return redirect('enrollments:cmtp_list')
    
    return render(request, 'enrollments/confirm_delete.html', {
        'object': cmtp,
        'object_type': 'CMTP Application'
    })




'''Associated Affiliation Views
These views handle the associated affiliation process, including creation, approval, rejection, and listing.

@login_required
@user_passes_test(is_admin, login_url='/', redirect_field_name=None)
def associated_reject(request, pk):
    """
    Admin rejects an AssociatedAffiliation, sends a notification email,
    and redirects back to the list.
    """
    obj = get_object_or_404(AssociatedAffiliation, pk=pk)

    if request.method == 'POST':
        # Mark as not approved (optional: you could add a `rejected` flag to the model)
        obj.approved = False
        obj.save()

        if DEBUG == True:
            pass
        else:
            # Send rejection email
            send_mail(
                subject="Your ACRP associated application has been rejected",
                message=(
                    f"Dear {obj.first_name} {obj.last_name},\n\n"
                    "We’re sorry to let you know that your associated-application "
                    "has not been approved.\n\n"
                    "If you believe this is in error or would like more information, "
                    "please contact support@acrpafrica.co.za\n\n"
                    "Kind regards,\n"
                    "The ACRP Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[obj.email],
                fail_silently=False,
            )

        messages.success(request, "Application rejected and email notification sent.")
        return redirect('enrollments:associated_list')

    # GET → show confirmation “Are you sure?”
    return render(request,
                  'enrollments/associated_reject_confirm.html',
                  {'object': obj})

@login_required
@permission_required('enrollments.view_associatedaffiliation', raise_exception=True)
def associated_list(request):
    return _list(request, AssociatedAffiliation, "enrollments/associated_list.html",
                 ['first_name', 'last_name','surname','email'])


# Generic create/update handler
def _crud(request, pk, model, form_class, formset_class, list_url, form_template):
    instance = get_object_or_404(model, pk=pk) if pk else None
    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        fs   = formset_class(request.POST, request.FILES, instance=instance)
        if form.is_valid() and fs.is_valid():
            obj = form.save()
            fs.instance = obj
            fs.save()
            messages.success(request, "Saved successfully.")
            return redirect(list_url)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = form_class(instance=instance)
        fs   = formset_class(instance=instance)
    return render(request, form_template, {'form': form, 'formset': fs})

def associated_success(request):
    """
    Display a thank-you page after an AssociatedAffiliation is created or updated.
    """
    return render(request, 'enrollments/associated_success.html')

# Associated CRUD
#@login_required
#@permission_required('enrollments.add_associatedaffiliation', raise_exception=True)
def associated_create(request):
    """
    Create a new AssociatedAffiliation + documents.
    On success, render the “thank you” page.
    """
    if request.method == 'POST':
        form    = AssociatedForm(request.POST, request.FILES)
        formset = AssocDocFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            # Save the affiliation
            obj = form.save(commit=False)
            obj.created_user = request.user
            obj.save()
            # Save documents
            formset.instance = obj
            formset.save()
            # Render success page
            return render(request,
                          'enrollments/associated_success.html',
                          {'application': obj})
    else:
        form    = AssociatedForm()
        formset = AssocDocFormSet()

    return render(request,
                  'enrollments/associated_form.html',
                  {'form': form, 'formset': formset})

@login_required
@permission_required('enrollments.change_associatedaffiliation', raise_exception=True)
def associated_update(request, pk):
    return _crud(request, pk, AssociatedAffiliation, AssociatedForm, AssocDocFormSet,
                 'enrollments:associated_list', "enrollments/associated_form.html")


# Single delete confirmation for all three models
@login_required
@permission_required('enrollments.delete_associatedaffiliation', raise_exception=True)
def application_delete(request, model_name, pk):
    model_map = {
        'associated': AssociatedAffiliation,
    }
    model = model_map.get(model_name)
    if not model:
        return HttpResponseForbidden("Invalid application type.")
    obj = get_object_or_404(model, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, "Deleted successfully.")
        return redirect(f'enrollments:{model_name}_list')
    return render(request, "enrollments/application_confirm_delete.html", {'object': obj})

@login_required
@user_passes_test(is_admin, login_url='/', redirect_field_name=None)
def associated_approve(request, pk):
    """
    Mark the affiliation approved, stamp who/when, then redirect.
    Our post_save signal will pick up the approved=True change,
    create the User + LearnerProfile and send the approval email.
    """
    obj = get_object_or_404(AssociatedAffiliation, pk=pk)

    obj.approved     = True
    obj.approved_by  = request.user
    obj.approved_at  = timezone.now()
    # Only these fields — avoids infinite loops
    obj.save(update_fields=['approved', 'approved_by', 'approved_at'])

    messages.success(request, "Associated application approved and user created.")
    return redirect('enrollments:associated_list')

'''

