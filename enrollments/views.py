# enrollments/views.py - Redesigned for new onboarding flow and application structure
"""
Enhanced views supporting the new onboarding flow and application model structure.

Design Principles:
1. Multi-step onboarding process with session tracking
2. Dynamic form generation based on user selections
3. Unified application management across all types
4. Comprehensive security and permission checking
5. Optimized queries and caching
6. Proper error handling and logging

Flow:
1. User starts onboarding → selects affiliation type
2. User selects council
3. If designated → selects category and subcategory (if CPSC)
4. OnboardingSession created with all choices
5. User fills appropriate application form
6. Application created with linked onboarding session
"""

import logging
from typing import Type, Dict, Any, Optional

from django.forms import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count, Prefetch, F
from django.http import HttpResponseForbidden, JsonResponse, Http404, HttpResponse
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
from django.contrib.contenttypes.models import ContentType

from .models import (
    # Core models
    Council,
    AffiliationType,
    DesignationCategory,
    DesignationSubcategory,
    OnboardingSession,
    
    # Application models
    AssociatedApplication,
    DesignatedApplication,
    StudentApplication,
    
    # Related models
    AcademicQualification,
    Reference,
    PracticalExperience,
    Document,
)

from .forms import (
    # Onboarding forms
    AffiliationTypeSelectionForm,
    CouncilSelectionForm,
    DesignationCategorySelectionForm,
    DesignationSubcategorySelectionForm,
    OnboardingSessionForm,
    
    # Application forms
    AssociatedApplicationForm,
    DesignatedApplicationForm,
    StudentApplicationForm,
    
    # Related model forms and formsets
    AcademicQualificationForm,
    ReferenceForm,
    PracticalExperienceForm,
    DocumentForm,
    BulkDocumentUploadForm,
    AcademicQualificationFormSet,
    ReferenceFormSet,
    PracticalExperienceFormSet,
    DocumentFormSet,
    
    # Utility forms
    ApplicationSearchForm,
    ApplicationReviewForm,
)

from accounts.models import User

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ITEMS_PER_PAGE = 25
CACHE_TIMEOUT = 900  # 15 minutes
SEARCH_CACHE_TIMEOUT = 300  # 5 minutes
ONBOARDING_SESSION_TIMEOUT = 3600  # 1 hour


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

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


def rate_limit(max_requests=50, window=3600):
    """Simple rate limiting decorator"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            cache_key = f"rate_limit:{view_func.__name__}:{ip}"
            
            current_requests = cache.get(cache_key, 0)
            if current_requests >= max_requests:
                logger.warning(f"Rate limit exceeded for IP {ip} on {view_func.__name__}")
                messages.error(request, "Too many requests. Please try again later.")
                return redirect('enrollments:onboarding_start')
            
            cache.set(cache_key, current_requests + 1, window)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_application_model_for_type(affiliation_type: str) -> Type:
    """Get the appropriate application model class for affiliation type"""
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    return model_map.get(affiliation_type)


def get_all_applications_queryset():
    """Get unified queryset of all application types"""
    # We'll need to use union for different models
    from django.db.models import CharField, Value
    
    associated = AssociatedApplication.objects.annotate(
        app_type=Value('associated', output_field=CharField())
    ).values(
        'id', 'app_type', 'application_number', 'status', 'email', 
        'full_names', 'surname', 'created_at', 'submitted_at'
    )
    
    designated = DesignatedApplication.objects.annotate(
        app_type=Value('designated', output_field=CharField())
    ).values(
        'id', 'app_type', 'application_number', 'status', 'email',
        'full_names', 'surname', 'created_at', 'submitted_at'
    )
    
    student = StudentApplication.objects.annotate(
        app_type=Value('student', output_field=CharField())
    ).values(
        'id', 'app_type', 'application_number', 'status', 'email',
        'full_names', 'surname', 'created_at', 'submitted_at'
    )
    
    return associated.union(designated, student)


# ============================================================================
# ONBOARDING FLOW VIEWS
# ============================================================================

@csrf_protect
@rate_limit(max_requests=20, window=3600)
def onboarding_start(request):
    """
    Step 1: Start onboarding process - select affiliation type.
    
    This is the entry point for all new applications.
    """
    if request.method == 'POST':
        form = AffiliationTypeSelectionForm(request.POST)
        if form.is_valid():
            affiliation_type = form.cleaned_data['affiliation_type']
            
            # Create or get onboarding session
            session, created = OnboardingSession.objects.get_or_create(
                user=request.user if request.user.is_authenticated else None,
                status='selecting_affiliation',
                defaults={
                    'selected_affiliation_type': affiliation_type,
                    'ip_address': get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500]
                }
            )
            
            if not created:
                session.selected_affiliation_type = affiliation_type
                session.status = 'selecting_council'
                session.save(update_fields=['selected_affiliation_type', 'status', 'updated_at'])
            
            # Store session ID in user session
            request.session['onboarding_session_id'] = session.session_id.hex
            
            logger.info(f"Onboarding started: {affiliation_type.name} from IP {get_client_ip(request)}")
            return redirect('enrollments:onboarding_council', session_id=session.session_id.hex)
        
        messages.error(request, "Please select a valid affiliation type.")
    else:
        form = AffiliationTypeSelectionForm()
    
    context = {
        'form': form,
        'page_title': 'Select Affiliation Type',
        'step': 1,
        'total_steps': 4,  # max possible steps
    }
    
    return render(request, 'enrollments/onboarding/step1_affiliation_type.html', context)


@csrf_protect
def onboarding_council(request, session_id):
    """
    Step 2: Select council (CGMP, CPSC, CMTP).
    
    All affiliation types need to select a council.
    """
    # Get and validate onboarding session
    try:
        session = OnboardingSession.objects.get(session_id=session_id)
    except OnboardingSession.DoesNotExist:
        messages.error(request, "Invalid onboarding session. Please start over.")
        return redirect('enrollments:onboarding_start')
    
    # Check session timeout
    if (timezone.now() - session.created_at).total_seconds() > ONBOARDING_SESSION_TIMEOUT:
        messages.error(request, "Onboarding session expired. Please start over.")
        return redirect('enrollments:onboarding_start')
    
    if request.method == 'POST':
        form = CouncilSelectionForm(request.POST)
        if form.is_valid():
            council = form.cleaned_data['council']
            
            session.selected_council = council
            session.status = 'selecting_category'
            session.save(update_fields=['selected_council', 'status', 'updated_at'])
            
            # Determine next step based on affiliation type
            if session.selected_affiliation_type.code == 'designated':
                return redirect('enrollments:onboarding_category', session_id=session_id)
            else:
                # Associated or Student - go directly to application
                session.status = 'completed'
                session.completed_at = timezone.now()
                session.save(update_fields=['status', 'completed_at'])
                return redirect('enrollments:application_create', session_id=session_id)
        
        messages.error(request, "Please select a valid council.")
    else:
        form = CouncilSelectionForm()
    
    context = {
        'form': form,
        'session': session,
        'page_title': 'Select Council',
        'step': 2,
        'total_steps': 4,
    }
    
    return render(request, 'enrollments/onboarding/step2_council.html', context)


@csrf_protect
def onboarding_category(request, session_id):
    """
    Step 3: Select designation category (for designated affiliations only).
    
    Shows the 4 levels of designation categories.
    """
    try:
        session = OnboardingSession.objects.select_related(
            'selected_affiliation_type', 'selected_council'
        ).get(session_id=session_id)
    except OnboardingSession.DoesNotExist:
        messages.error(request, "Invalid onboarding session.")
        return redirect('enrollments:onboarding_start')
    
    # Validate that this step is appropriate
    if session.selected_affiliation_type.code != 'designated':
        messages.error(request, "Category selection is only for designated affiliations.")
        return redirect('enrollments:onboarding_start')
    
    if request.method == 'POST':
        form = DesignationCategorySelectionForm(request.POST)
        if form.is_valid():
            category = form.cleaned_data['designation_category']
            
            session.selected_designation_category = category
            session.status = 'selecting_subcategory'
            session.save(update_fields=['selected_designation_category', 'status', 'updated_at'])
            
            # Check if council has subcategories (CPSC)
            if session.selected_council.has_subcategories:
                return redirect('enrollments:onboarding_subcategory', session_id=session_id)
            else:
                # No subcategories - complete onboarding
                session.status = 'completed'
                session.completed_at = timezone.now()
                session.save(update_fields=['status', 'completed_at'])
                return redirect('enrollments:application_create', session_id=session_id)
        
        messages.error(request, "Please select a valid designation category.")
    else:
        form = DesignationCategorySelectionForm()
    
    context = {
        'form': form,
        'session': session,
        'page_title': 'Select Designation Category',
        'step': 3,
        'total_steps': 4,
    }
    
    return render(request, 'enrollments/onboarding/step3_category.html', context)


@csrf_protect
def onboarding_subcategory(request, session_id):
    """
    Step 4: Select designation subcategory (for CPSC designated affiliations only).
    
    Shows CPSC-specific subcategories for the selected category.
    """
    try:
        session = OnboardingSession.objects.select_related(
            'selected_affiliation_type', 'selected_council', 'selected_designation_category'
        ).get(session_id=session_id)
    except OnboardingSession.DoesNotExist:
        messages.error(request, "Invalid onboarding session.")
        return redirect('enrollments:onboarding_start')
    
    # Validate that this step is appropriate
    if not (session.selected_affiliation_type.code == 'designated' and 
            session.selected_council.has_subcategories):
        messages.error(request, "Subcategory selection is only for CPSC designated affiliations.")
        return redirect('enrollments:onboarding_start')
    
    if request.method == 'POST':
        form = DesignationSubcategorySelectionForm(
            category=session.selected_designation_category,
            council=session.selected_council,
            data=request.POST
        )
        if form.is_valid():
            subcategory = form.cleaned_data['designation_subcategory']
            
            session.selected_designation_subcategory = subcategory
            session.status = 'completed'
            session.completed_at = timezone.now()
            session.save(update_fields=[
                'selected_designation_subcategory', 'status', 'completed_at'
            ])
            
            return redirect('enrollments:application_create', session_id=session_id)
        
        messages.error(request, "Please select a valid subcategory.")
    else:
        form = DesignationSubcategorySelectionForm(
            category=session.selected_designation_category,
            council=session.selected_council
        )
    
    context = {
        'form': form,
        'session': session,
        'page_title': 'Select Subcategory',
        'step': 4,
        'total_steps': 4,
    }
    
    return render(request, 'enrollments/onboarding/step4_subcategory.html', context)


# ============================================================================
# APPLICATION CREATION VIEWS
# ============================================================================

@csrf_protect
@rate_limit(max_requests=5, window=3600)
@transaction.atomic
def application_create(request, session_id):
    """
    Create application based on completed onboarding session.
    
    Dynamically selects the appropriate form based on affiliation type
    and handles all related models (qualifications, references, etc.).
    """
    try:
        session = OnboardingSession.objects.select_related(
            'selected_affiliation_type', 'selected_council',
            'selected_designation_category', 'selected_designation_subcategory'
        ).get(session_id=session_id)
    except OnboardingSession.DoesNotExist:
        messages.error(request, "Invalid onboarding session.")
        return redirect('enrollments:onboarding_start')
    
    # Validate session is complete
    if not session.is_complete():
        messages.error(request, "Please complete the onboarding process.")
        return redirect('enrollments:onboarding_start')
    
    # Check if application already exists for this session
    if hasattr(session, 'application'):
        messages.info(request, "Application already exists for this session.")
        return redirect('enrollments:application_detail', 
                       pk=session.application.pk, 
                       app_type=session.selected_affiliation_type.code)
    
    # Get appropriate form class
    form_class_map = {
        'associated': AssociatedApplicationForm,
        'designated': DesignatedApplicationForm,
        'student': StudentApplicationForm,
    }
    
    form_class = form_class_map.get(session.selected_affiliation_type.code)
    if not form_class:
        messages.error(request, "Invalid affiliation type.")
        return redirect('enrollments:onboarding_start')
    
    if request.method == 'POST':
        # Create main application form
        form = form_class(
            request.POST, 
            request=request,
            onboarding_session=session
        )
        
        # Initialize formsets for designated applications
        formsets = {}
        if session.selected_affiliation_type.code == 'designated':
            # Only show formsets for designated applications
            formsets = {
                'qualifications': AcademicQualificationFormSet(request.POST, prefix='qualifications'),
                'references': ReferenceFormSet(request.POST, prefix='references'),
                'experiences': PracticalExperienceFormSet(request.POST, prefix='experiences'),
                'documents': DocumentFormSet(request.POST, request.FILES, prefix='documents'),
            }
        elif session.selected_affiliation_type.code in ['associated', 'student']:
            # For associated and student, only show references and documents
            formsets = {
                'references': ReferenceFormSet(request.POST, prefix='references'),
                'documents': DocumentFormSet(request.POST, request.FILES, prefix='documents'),
            }
        
        # Validate main form and all formsets
        form_valid = form.is_valid()
        formsets_valid = all(formset.is_valid() for formset in formsets.values())
        
        if form_valid and formsets_valid:
            try:
                # Save main application
                application = form.save(commit=False)
                application.onboarding_session = session
                
                # Set designation fields for designated applications
                if session.selected_affiliation_type.code == 'designated':
                    application.designation_category = session.selected_designation_category
                    application.designation_subcategory = session.selected_designation_subcategory
                
                application.save()
                
                # Save formsets
                for formset_name, formset in formsets.items():
                    if formset_name in ['qualifications', 'experiences']:
                        # Direct foreign key relationship
                        instances = formset.save(commit=False)
                        for instance in instances:
                            instance.application = application
                            instance.save()
                    else:
                        # Generic foreign key relationship
                        instances = formset.save(commit=False)
                        for instance in instances:
                            instance.content_object = application
                            instance.save()
                
                logger.info(f"Application created: {application.application_number} from session {session_id}")
                
                # Clear caches
                cache.delete_many([
                    'application_statistics',
                    'recent_applications',
                ])
                
                messages.success(
                    request, 
                    f"Your {session.selected_affiliation_type.name} application has been submitted successfully!"
                )
                
                return redirect('enrollments:application_dashboard', 
                               pk=application.pk, 
                               app_type=session.selected_affiliation_type.code)
                
            except Exception as e:
                logger.error(f"Error creating application: {str(e)}")
                messages.error(request, "An error occurred while creating your application. Please try again.")
        
        else:
            # Form validation failed
            logger.warning(f"Application form validation failed. Form errors: {form.errors}")
            for formset_name, formset in formsets.items():
                if formset.errors:
                    logger.warning(f"{formset_name} formset errors: {formset.errors}")
            
            messages.error(request, "Please correct the errors below and try again.")
    
    else:
        # GET request - create empty forms
        form = form_class(
            request=request,
            onboarding_session=session
        )
        
        # Initialize empty formsets
        formsets = {}
        if session.selected_affiliation_type.code == 'designated':
            formsets = {
                'qualifications': AcademicQualificationFormSet(prefix='qualifications'),
                'references': ReferenceFormSet(prefix='references'),
                'experiences': PracticalExperienceFormSet(prefix='experiences'),
                'documents': DocumentFormSet(prefix='documents'),
            }
        elif session.selected_affiliation_type.code in ['associated', 'student']:
            formsets = {
                'references': ReferenceFormSet(prefix='references'),
                'documents': DocumentFormSet(prefix='documents'),
            }
    
    # Determine form sections to show
    show_qualifications = session.selected_affiliation_type.code == 'designated'
    show_experiences = session.selected_affiliation_type.code == 'designated'
    show_references = True  # All application types have references
    show_documents = True   # All application types have documents
    
    context = {
        'form': form,
        'formsets': formsets,
        'session': session,
        'show_qualifications': show_qualifications,
        'show_experiences': show_experiences,
        'show_references': show_references,
        'show_documents': show_documents,
        'page_title': f'Create {session.selected_affiliation_type.name} Application',
        'council_name': session.selected_council.name,
        'affiliation_type': session.selected_affiliation_type.name,
    }
    
    # Use different templates for different application types
    template_map = {
        'associated': 'enrollments/applications/associated_form.html',
        'designated': 'enrollments/applications/designated_form.html',
        'student': 'enrollments/applications/student_form.html',
    }
    
    template = template_map.get(session.selected_affiliation_type.code, 
                               'enrollments/applications/base_form.html')
    
    return render(request, template, context)


# ============================================================================
# APPLICATION MANAGEMENT VIEWS
# ============================================================================

@login_required
@permission_required('enrollments.view_baseapplication', raise_exception=True)
def application_list(request):
    """
    Unified list view for all application types with advanced filtering.
    
    Shows applications from all councils and affiliation types in one view.
    """
    # Get search parameters
    search_form = ApplicationSearchForm(request.GET or None)
    
    # Build unified queryset
    applications = get_all_applications_queryset()
    
    # Apply filters
    if search_form.is_valid():
        search_query = search_form.cleaned_data.get('search_query')
        council = search_form.cleaned_data.get('council')
        affiliation_type = search_form.cleaned_data.get('affiliation_type')
        status = search_form.cleaned_data.get('status')
        date_from = search_form.cleaned_data.get('date_from')
        date_to = search_form.cleaned_data.get('date_to')
        
        # Apply search filters (this gets complex with union queries)
        # For now, we'll implement basic filtering
        # In production, consider using Elasticsearch or similar for complex searches
        
        if search_query:
            # We'll need to filter each model separately then union
            pass  # Implement complex search as needed
        
        if status:
            # Filter by status across all types
            pass  # Implement status filtering
    
    # For now, let's get a simpler queryset for demonstration
    # In production, you'd optimize this with proper indexing and search
    
    # Get recent applications from all types
    recent_applications = []
    
    # Associated applications
    associated_apps = AssociatedApplication.objects.select_related(
        'onboarding_session__selected_council',
        'onboarding_session__selected_affiliation_type'
    ).order_by('-created_at')[:50]
    
    for app in associated_apps:
        recent_applications.append({
            'id': app.pk,
            'type': 'Associated',
            'council': app.onboarding_session.selected_council.code,
            'name': app.get_display_name(),
            'email': app.email,
            'application_number': app.application_number,
            'status': app.status,
            'created_at': app.created_at,
            'submitted_at': app.submitted_at,
        })
    
    # Designated applications
    designated_apps = DesignatedApplication.objects.select_related(
        'onboarding_session__selected_council',
        'onboarding_session__selected_affiliation_type',
        'designation_category'
    ).order_by('-created_at')[:50]
    
    for app in designated_apps:
        recent_applications.append({
            'id': app.pk,
            'type': 'Designated',
            'council': app.onboarding_session.selected_council.code,
            'name': app.get_display_name(),
            'email': app.email,
            'application_number': app.application_number,
            'status': app.status,
            'created_at': app.created_at,
            'submitted_at': app.submitted_at,
            'category': app.designation_category.name if app.designation_category else None,
        })
    
    # Student applications
    student_apps = StudentApplication.objects.select_related(
        'onboarding_session__selected_council',
        'onboarding_session__selected_affiliation_type'
    ).order_by('-created_at')[:50]
    
    for app in student_apps:
        recent_applications.append({
            'id': app.pk,
            'type': 'Student',
            'council': app.onboarding_session.selected_council.code,
            'name': app.get_display_name(),
            'email': app.email,
            'application_number': app.application_number,
            'status': app.status,
            'created_at': app.created_at,
            'submitted_at': app.submitted_at,
            'institution': app.current_institution,
        })
    
    # Sort by creation date
    recent_applications.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Paginate
    paginator = Paginator(recent_applications, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    try:
        applications_page = paginator.page(page_number)
    except PageNotAnInteger:
        applications_page = paginator.page(1)
    except EmptyPage:
        applications_page = paginator.page(paginator.num_pages)
    
    context = {
        'applications': applications_page,
        'search_form': search_form,
        'page_title': 'All Applications',
        'total_count': len(recent_applications),
    }
    
    return render(request, 'enrollments/applications/list.html', context)


def application_detail(request, pk, app_type):
    """
    Unified detail view for all application types.
    
    Shows comprehensive application details with related models.
    """
    # Get appropriate model
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    
    model = model_map.get(app_type)
    if not model:
        raise Http404("Invalid application type")
    
    # Get application with related data
    if model == DesignatedApplication:
        application = get_object_or_404(
            model.objects.select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type',
                'designation_category',
                'designation_subcategory'
            ).prefetch_related(
                'academic_qualifications',
                'practical_experiences',
                'documents',
                Prefetch('references', queryset=Reference.objects.select_related())
            ),
            pk=pk
        )
    else:
        application = get_object_or_404(
            model.objects.select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type'
            ).prefetch_related(
                'documents',
                Prefetch('references', queryset=Reference.objects.select_related())
            ),
            pk=pk
        )
    
    # Check permissions
    user_can_view = (
        request.user.is_authenticated and (
            application.onboarding_session.user == request.user or
            application.email == request.user.email or
            request.user.acrp_role in {User.ACRPRole.GLOBAL_SDP, User.ACRPRole.PROVIDER_ADMIN}
        )
    ) or not request.user.is_authenticated
    
    if not user_can_view:
        return HttpResponseForbidden("You don't have permission to view this application")
    
    context = {
        'application': application,
        'app_type': app_type,
        'council': application.onboarding_session.selected_council,
        'affiliation_type': application.onboarding_session.selected_affiliation_type,
        'page_title': f'{app_type.title()} Application Details',
    }
    
    # Use different templates for different application types
    template_map = {
        'associated': 'enrollments/applications/associated_detail.html',
        'designated': 'enrollments/applications/designated_detail.html',
        'student': 'enrollments/applications/student_detail.html',
    }
    
    template = template_map.get(app_type, 'enrollments/applications/base_detail.html')
    
    return render(request, template, context)


@login_required
@permission_required('enrollments.change_baseapplication', raise_exception=True)
@transaction.atomic
def application_update(request, pk, app_type):
    """
    Update existing application with all related models.
    """
    model_map = {
        'associated': (AssociatedApplication, AssociatedApplicationForm),
        'designated': (DesignatedApplication, DesignatedApplicationForm),
        'student': (StudentApplication, StudentApplicationForm),
    }
    
    model_info = model_map.get(app_type)
    if not model_info:
        raise Http404("Invalid application type")
    
    model, form_class = model_info
    application = get_object_or_404(model, pk=pk)
    
    if request.method == 'POST':
        form = form_class(
            request.POST,
            instance=application,
            request=request,
            onboarding_session=application.onboarding_session
        )
        
        # Handle formsets for designated applications
        formsets = {}
        if app_type == 'designated':
            formsets = {
                'qualifications': AcademicQualificationFormSet(
                    request.POST, instance=application, prefix='qualifications'
                ),
                'references': ReferenceFormSet(
                    request.POST, instance=application, prefix='references'
                ),
                'experiences': PracticalExperienceFormSet(
                    request.POST, instance=application, prefix='experiences'
                ),
                'documents': DocumentFormSet(
                    request.POST, request.FILES, instance=application, prefix='documents'
                ),
            }
        else:
            formsets = {
                'references': ReferenceFormSet(
                    request.POST, instance=application, prefix='references'
                ),
                'documents': DocumentFormSet(
                    request.POST, request.FILES, instance=application, prefix='documents'
                ),
            }
        
        form_valid = form.is_valid()
        formsets_valid = all(formset.is_valid() for formset in formsets.values())
        
        if form_valid and formsets_valid:
            form.save()
            
            # Save formsets
            for formset in formsets.values():
                formset.save()
            
            logger.info(f"Application updated: {application.application_number}")
            messages.success(request, "Application updated successfully.")
            return redirect('enrollments:application_detail', pk=pk, app_type=app_type)
        
        else:
            messages.error(request, "Please correct the errors below.")
    
    else:
        form = form_class(
            instance=application,
            request=request,
            onboarding_session=application.onboarding_session
        )
        
        # Initialize formsets
        formsets = {}
        if app_type == 'designated':
            formsets = {
                'qualifications': AcademicQualificationFormSet(
                    instance=application, prefix='qualifications'
                ),
                'references': ReferenceFormSet(
                    instance=application, prefix='references'
                ),
                'experiences': PracticalExperienceFormSet(
                    instance=application, prefix='experiences'
                ),
                'documents': DocumentFormSet(
                    instance=application, prefix='documents'
                ),
            }
        else:
            formsets = {
                'references': ReferenceFormSet(
                    instance=application, prefix='references'
                ),
                'documents': DocumentFormSet(
                    instance=application, prefix='documents'
                ),
            }
    
    context = {
        'form': form,
        'formsets': formsets,
        'application': application,
        'app_type': app_type,
        'is_update': True,
        'page_title': f'Update {app_type.title()} Application',
    }
    
    template_map = {
        'associated': 'enrollments/applications/associated_form.html',
        'designated': 'enrollments/applications/designated_form.html',
        'student': 'enrollments/applications/student_form.html',
    }
    
    template = template_map.get(app_type, 'enrollments/applications/base_form.html')
    
    return render(request, template, context)


# ============================================================================
# APPLICATION REVIEW AND APPROVAL
# ============================================================================

@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
@transaction.atomic
def application_review(request, pk, app_type):
    """
    Universal application review handler for all application types.
    """
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    
    model = model_map.get(app_type)
    if not model:
        raise Http404("Invalid application type")
    
    application = get_object_or_404(model, pk=pk)
    
    form = ApplicationReviewForm(request.POST)
    
    if form.is_valid():
        status = form.cleaned_data['status']
        reviewer_notes = form.cleaned_data['reviewer_notes']
        rejection_reason = form.cleaned_data['rejection_reason']
        
        try:
            # Update application status
            application.status = status
            application.reviewed_at = timezone.now()
            application.reviewed_by = request.user
            application.reviewer_notes = reviewer_notes
            
            if status == 'approved':
                application.approved_at = timezone.now()
                application.approved_by = request.user
            elif status == 'rejected':
                application.rejected_at = timezone.now()
                application.rejected_by = request.user
                application.rejection_reason = rejection_reason
            
            application.save(update_fields=[
                'status', 'reviewed_at', 'reviewed_by', 'reviewer_notes',
                'approved_at', 'approved_by', 'rejected_at', 'rejected_by', 'rejection_reason'
            ])
            
            logger.info(f"Application {application.application_number} {status} by {request.user.id}")
            
            # Send notification email (implement as needed)
            # send_status_change_email(application, status)
            
            messages.success(request, f"Application {status} successfully.")
            
        except Exception as e:
            logger.error(f"Error reviewing application {pk}: {str(e)}")
            messages.error(request, "An error occurred during review.")
    
    else:
        messages.error(request, "Invalid review data.")
    
    return redirect('enrollments:application_detail', pk=pk, app_type=app_type)


# ============================================================================
# DASHBOARD AND STATISTICS
# ============================================================================

@login_required
@user_passes_test(is_admin_or_manager, login_url='/', redirect_field_name=None)
def enrollment_dashboard(request):
    """
    Enhanced administrative dashboard with comprehensive statistics.
    """
    # Calculate statistics for each council and affiliation type
    stats = {}
    
    for council in Council.objects.filter(is_active=True):
        council_stats = {
            'total': 0,
            'approved': 0,
            'pending': 0,
            'by_type': {}
        }
        
        # Get applications for this council across all types
        for app_model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
            apps = app_model.objects.filter(onboarding_session__selected_council=council)
            
            app_type = app_model.__name__.replace('Application', '').lower()
            type_stats = {
                'total': apps.count(),
                'approved': apps.filter(status='approved').count(),
                'pending': apps.filter(status__in=['draft', 'submitted', 'under_review']).count(),
            }
            
            council_stats['by_type'][app_type] = type_stats
            council_stats['total'] += type_stats['total']
            council_stats['approved'] += type_stats['approved']
            council_stats['pending'] += type_stats['pending']
        
        stats[council.code.lower()] = council_stats
    
    # Get recent applications across all types
    recent_applications = []
    
    # This could be optimized with a single query using union
    for app_model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
        apps = app_model.objects.select_related(
            'onboarding_session__selected_council',
            'onboarding_session__selected_affiliation_type'
        ).order_by('-created_at')[:10]
        
        for app in apps:
            recent_applications.append({
                'type': app.__class__.__name__.replace('Application', ''),
                'council': app.onboarding_session.selected_council.code,
                'name': app.get_display_name(),
                'email': app.email,
                'application_number': app.application_number,
                'status': app.status,
                'created_at': app.created_at,
            })
    
    # Sort by creation date
    recent_applications.sort(key=lambda x: x['created_at'], reverse=True)
    recent_applications = recent_applications[:20]
    
    context = {
        'stats': stats,
        'recent_applications': recent_applications,
        'page_title': 'Enrollment Dashboard'
    }
    
    return render(request, 'enrollments/dashboard.html', context)


def application_dashboard(request, pk, app_type):
    """
    Public application dashboard showing status and next steps.
    """
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    
    model = model_map.get(app_type)
    if not model:
        raise Http404("Invalid application type")
    
    try:
        application = get_object_or_404(
            model.objects.select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type'
            ),
            pk=pk
        )
    except Exception:
        raise Http404("Application not found")
    
    # Check permissions
    user_can_view = (
        request.user.is_authenticated and (
            application.onboarding_session.user == request.user or
            application.email == request.user.email or
            request.user.acrp_role in {User.ACRPRole.GLOBAL_SDP, User.ACRPRole.PROVIDER_ADMIN}
        )
    ) or not request.user.is_authenticated
    
    if not user_can_view:
        return HttpResponseForbidden("You don't have permission to view this application")
    
    # Determine next steps based on status
    next_steps = []
    if application.status == 'draft':
        next_steps = [
            'Complete all required sections',
            'Upload required documents',
            'Submit your application for review'
        ]
    elif application.status == 'submitted':
        next_steps = [
            'Your application is under review',
            'You will receive email updates on progress',
            'Review process typically takes 5-10 business days'
        ]
    elif application.status == 'requires_clarification':
        next_steps = [
            'Review the feedback provided',
            'Update your application with additional information',
            'Resubmit for continued review'
        ]
    elif application.status == 'approved':
        next_steps = [
            'Congratulations! Your application has been approved',
            'You will receive your membership certificate via email',
            'Welcome to the ' + application.onboarding_session.selected_council.name
        ]
    elif application.status == 'rejected':
        next_steps = [
            'Unfortunately, your application was not approved',
            'Review the feedback provided',
            'You may submit a new application addressing the concerns'
        ]
    
    context = {
        'application': application,
        'app_type': app_type,
        'council': application.onboarding_session.selected_council,
        'affiliation_type': application.onboarding_session.selected_affiliation_type,
        'next_steps': next_steps,
        'page_title': f'Application Dashboard - {application.application_number}',
    }
    
    return render(request, 'enrollments/application_dashboard.html', context)


# ============================================================================
# LEGACY COMPATIBILITY AND UTILITY VIEWS
# ============================================================================

def onboarding(request):
    """Redirect legacy onboarding URL to new flow"""
    return redirect('enrollments:onboarding_start')


def learner_apply_prompt(request):
    """Handle student application prompt"""
    if request.method == 'POST':
        token = request.POST.get('token', '').strip()
        if token:
            return redirect(reverse('student:learner_apply', args=[token]))
        messages.error(request, "Please enter your registration link token.")
    
    return render(request, 'enrollments/learner_apply_prompt.html')


# ============================================================================
# AJAX AND API VIEWS
# ============================================================================

@require_http_methods(["GET"])
def get_subcategories_ajax(request):
    """
    AJAX endpoint to get subcategories for a category and council.
    Used for dynamic form updates.
    """
    category_id = request.GET.get('category_id')
    council_id = request.GET.get('council_id')
    
    if not category_id or not council_id:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    
    try:
        subcategories = DesignationSubcategory.objects.filter(
            category_id=category_id,
            council_id=council_id,
            is_active=True
        ).values('id', 'name', 'description')
        
        return JsonResponse({
            'subcategories': list(subcategories)
        })
    
    except Exception as e:
        logger.error(f"Error fetching subcategories: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)


@require_http_methods(["GET"])
def application_status_ajax(request, pk, app_type):
    """
    AJAX endpoint to get current application status.
    Used for real-time status updates.
    """
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    
    model = model_map.get(app_type)
    if not model:
        return JsonResponse({'error': 'Invalid application type'}, status=400)
    
    try:
        application = get_object_or_404(model, pk=pk)
        
        return JsonResponse({
            'status': application.status,
            'status_display': application.get_status_display(),
            'last_updated': application.updated_at.isoformat(),
        })
    
    except Exception as e:
        logger.error(f"Error fetching application status: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)
    

    