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
def onboarding_start(request):
    """
    Step 1: Start onboarding process - select affiliation type.
    """
    if request.method == 'POST':
        # Get the string value from POST
        affiliation_type_code = request.POST.get('affiliation_type')
        
        if affiliation_type_code in ['associated', 'designated', 'student']:
            try:
                # Get the actual AffiliationType object
                affiliation_type = AffiliationType.objects.get(
                    code=affiliation_type_code,
                    is_active=True
                )
                
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
                
                # Store session ID in user session (with dashes)
                request.session['onboarding_session_id'] = str(session.session_id)
                
                logger.info(f"Onboarding started: {affiliation_type.name} from IP {get_client_ip(request)}")
                
                # Redirect with full UUID format (with dashes)
                return redirect('enrollments:onboarding_council', session_id=str(session.session_id))
                
            except AffiliationType.DoesNotExist:
                messages.error(request, f"Invalid affiliation type: {affiliation_type_code}")
        else:
            messages.error(request, "Please select a valid affiliation type.")
    
    # For GET request or form errors
    form = AffiliationTypeSelectionForm()
    
    context = {
        'form': form,
        'page_title': 'Select Affiliation Type',
        'step': 1,
        'total_steps': 4,
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
        # Get council ID from POST data
        council_id = request.POST.get('council')
        logger.info(f"POST data received: {request.POST}")
        logger.info(f"Council ID: {council_id}")
        
        if council_id:
            try:
                # Get the actual Council object
                council = Council.objects.get(id=council_id, is_active=True)
                
                session.selected_council = council
                session.status = 'selecting_category'
                session.save(update_fields=['selected_council', 'status', 'updated_at'])
                
                logger.info(f"Council selected: {council.code} - {council.name}")
                
                # Determine next step based on affiliation type
                if session.selected_affiliation_type.code == 'designated':
                    return redirect('enrollments:onboarding_category', session_id=session_id)
                else:
                    # Associated or Student - go directly to application
                    session.status = 'completed'
                    session.completed_at = timezone.now()
                    session.save(update_fields=['status', 'completed_at'])
                    return redirect('enrollments:application_create', session_id=session_id)
                    
            except Council.DoesNotExist:
                logger.error(f"Council with ID {council_id} not found")
                messages.error(request, f"Invalid council selected: {council_id}")
        else:
            messages.error(request, "Please select a valid council.")
    
    # Get all councils for the template
    councils = Council.objects.filter(is_active=True).order_by('code')
    
    # Create a dictionary for easy access in template
    councils_dict = {}
    for council in councils:
        councils_dict[council.code.lower()] = council
    
    # Debug: Log available councils
    logger.info(f"Available councils: {[(c.code, c.id) for c in councils]}")
    
    form = CouncilSelectionForm()
    
    context = {
        'form': form,
        'session': session,
        'councils': councils_dict,  # For template access like {{ councils.cgmp.id }}
        'councils_list': councils,   # For iteration in template
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

from django.contrib.contenttypes.models import ContentType
import traceback 

@csrf_protect
@rate_limit(max_requests=102, window=3600)
@transaction.atomic
def application_create(request, session_id):
    """
    Create application with proper document handling for generic formsets.
    """
    try:
        session = OnboardingSession.objects.select_related(
            'selected_affiliation_type', 'selected_council',
            'selected_designation_category', 'selected_designation_subcategory'
        ).get(session_id=session_id)
    except OnboardingSession.DoesNotExist:
        messages.error(request, "Invalid onboarding session.")
        return redirect('enrollments:onboarding_start')
    
    if not session.is_complete():
        messages.error(request, "Please complete the onboarding process.")
        return redirect('enrollments:onboarding_start')
    
    # Check for existing application
    existing_application = None
    try:
        if session.selected_affiliation_type.code == 'associated':
            existing_application = AssociatedApplication.objects.get(onboarding_session=session)
        elif session.selected_affiliation_type.code == 'designated':
            existing_application = DesignatedApplication.objects.get(onboarding_session=session)
        elif session.selected_affiliation_type.code == 'student':
            existing_application = StudentApplication.objects.get(onboarding_session=session)
    except (AssociatedApplication.DoesNotExist, DesignatedApplication.DoesNotExist, StudentApplication.DoesNotExist):
        pass
    
    if existing_application:
        messages.info(request, "Application already exists for this session.")
        return redirect('enrollments:application_detail', 
                       pk=existing_application.pk, 
                       app_type=session.selected_affiliation_type.code)
    
    # Get form class
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
        logger.info(f"POST data keys: {list(request.POST.keys())}")
        logger.info(f"FILES data keys: {list(request.FILES.keys())}")
        
        # Create main form
        form = form_class(request.POST, request=request, onboarding_session=session)
        
        # For new applications, we need to handle documents differently
        # Extract document data manually instead of using generic formset
        document_data = extract_document_data_from_post(request)
        reference_data = extract_reference_data_from_post(request)
        
        # Initialize non-generic formsets
        formsets = {}
        if session.selected_affiliation_type.code == 'designated':
            formsets = {
                'qualifications': AcademicQualificationFormSet(request.POST, prefix='qualifications'),
                'experiences': PracticalExperienceFormSet(request.POST, prefix='experiences'),
            }
        
        # Validate main form
        form_valid = form.is_valid()
        if not form_valid:
            logger.warning(f"Main form errors: {form.errors}")
        
        # Validate formsets
        formsets_valid = all(formset.is_valid() for formset in formsets.values())
        
        # Validate extracted document data
        documents_valid, document_errors = validate_extracted_documents(document_data)
        references_valid, reference_errors = validate_extracted_references(reference_data)
        
        if form_valid and formsets_valid and documents_valid and references_valid:
            try:
                # Save main application first
                application = form.save(commit=False)
                application.onboarding_session = session
                
                if session.selected_affiliation_type.code == 'designated':
                    application.designation_category = session.selected_designation_category
                    application.designation_subcategory = session.selected_designation_subcategory
                
                application.save()
                logger.info(f"Application saved with ID: {application.pk}")
                
                # Get content type
                content_type = ContentType.objects.get_for_model(application.__class__)
                
                # Save non-generic formsets
                for formset_name, formset in formsets.items():
                    formset.instance = application
                    formset.save()
                    logger.info(f"Saved {formset_name} formset")
                
                # Save documents manually
                documents_saved = save_extracted_documents(document_data, application, content_type, request.user)
                logger.info(f"Saved {documents_saved} documents")
                
                # Save references manually
                references_saved = save_extracted_references(reference_data, application, content_type)
                logger.info(f"Saved {references_saved} references")
                
                # Verify documents were saved
                saved_documents = Document.objects.filter(content_type=content_type, object_id=application.pk)
                logger.info(f"Total documents in DB: {saved_documents.count()}")
                
                request.session['application_success'] = {
                    'application_number': application.application_number,
                    'affiliation_type': session.selected_affiliation_type.name,
                    'council_name': session.selected_council.name,
                    'application_id': application.pk,
                    'app_type': session.selected_affiliation_type.code,
                }
                
                return redirect('enrollments:application_success')
                
            except Exception as e:
                logger.error(f"Error creating application: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                messages.error(request, f"An error occurred: {str(e)}")
        
        else:
            # Show validation errors
            if not form_valid:
                messages.error(request, "Please correct the form errors.")
            if document_errors:
                messages.error(request, f"Document errors: {'; '.join(document_errors)}")
            if reference_errors:
                messages.error(request, f"Reference errors: {'; '.join(reference_errors)}")
    
    else:
        # GET request
        form = form_class(request=request, onboarding_session=session)
        formsets = {}
        if session.selected_affiliation_type.code == 'designated':
            formsets = {
                'qualifications': AcademicQualificationFormSet(prefix='qualifications'),
                'experiences': PracticalExperienceFormSet(prefix='experiences'),
            }
    
    # Create mock formsets for template
    formsets['references'] = create_mock_reference_formset()
    formsets['documents'] = create_mock_document_formset()
    
    context = {
        'form': form,
        'formsets': formsets,
        'session': session,
        'show_qualifications': session.selected_affiliation_type.code == 'designated',
        'show_experiences': session.selected_affiliation_type.code == 'designated',
        'show_references': True,
        'show_documents': True,
        'page_title': f'Create {session.selected_affiliation_type.name} Application',
        'council_name': session.selected_council.name,
        'affiliation_type': session.selected_affiliation_type.name,
    }
    
    template_map = {
        'associated': 'enrollments/applications/associated_form.html',
        'designated': 'enrollments/applications/designated_form.html',
        'student': 'enrollments/applications/student_form.html',
    }
    
    template = template_map.get(session.selected_affiliation_type.code, 
                               'enrollments/applications/base_form.html')
    
    return render(request, template, context)




# ============================================================================
# DOCUMENT MANAGEMENT VIEWS
# ============================================================================

@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
def document_verify(request, pk):
    """Verify a document"""
    document = get_object_or_404(Document, pk=pk)
    
    notes = request.POST.get('notes', '')
    document.verify(verified_by=request.user, notes=notes)
    
    messages.success(request, f'Document "{document.title}" verified successfully.')
    
    # Return to application detail
    app = document.content_object
    app_type = app.get_affiliation_type()
    return redirect('enrollments:application_detail', pk=app.pk, app_type=app_type)


@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
def document_reject(request, pk):
    """Reject a document"""
    document = get_object_or_404(Document, pk=pk)
    
    notes = request.POST.get('notes', 'Document rejected by reviewer')
    document.verified = False
    document.verified_by = request.user
    document.verified_at = timezone.now()
    document.verification_notes = notes
    document.save()
    
    messages.warning(request, f'Document "{document.title}" rejected.')
    
    # Return to application detail
    app = document.content_object
    app_type = app.get_affiliation_type()
    return redirect('enrollments:application_detail', pk=app.pk, app_type=app_type)


@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
def document_delete(request, pk):
    """Delete a document"""
    document = get_object_or_404(Document, pk=pk)
    app = document.content_object
    app_type = app.get_affiliation_type()
    
    document_title = document.title
    document.delete()
    
    messages.success(request, f'Document "{document_title}" deleted successfully.')
    return redirect('enrollments:application_detail', pk=app.pk, app_type=app_type)


# ============================================================================
# REFERENCE MANAGEMENT VIEWS
# ============================================================================

@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
def reference_approve(request, pk):
    """Mark reference as approved"""
    reference = get_object_or_404(Reference, pk=pk)
    
    reference.letter_received = True
    reference.letter_received_date = timezone.now()
    reference.save()
    
    messages.success(request, f'Reference from {reference.get_reference_full_name()} approved.')
    
    # Return to application detail
    app = reference.content_object
    app_type = app.get_affiliation_type()
    return redirect('enrollments:application_detail', pk=app.pk, app_type=app_type)




# ============================================================================
# 2. HELPER FUNCTIONS FOR MANUAL DOCUMENT PROCESSING
# ============================================================================

def extract_document_data_from_post(request):
    """Extract document data from POST request manually."""
    document_data = []
    
    # Get total forms from management form
    total_forms = int(request.POST.get('documents-TOTAL_FORMS', 0))
    
    for i in range(total_forms):
        # Check if this form has data
        category = request.POST.get(f'documents-{i}-category')
        title = request.POST.get(f'documents-{i}-title')
        file_key = f'documents-{i}-file'
        
        if category and title and file_key in request.FILES:
            document_data.append({
                'index': i,
                'category': category,
                'title': title,
                'description': request.POST.get(f'documents-{i}-description', ''),
                'file': request.FILES[file_key],
                'is_required': request.POST.get(f'documents-{i}-is_required') == 'on',
            })
    
    return document_data

def extract_reference_data_from_post(request):
    """Extract reference data from POST request manually."""
    reference_data = []
    
    total_forms = int(request.POST.get('references-TOTAL_FORMS', 0))
    
    for i in range(total_forms):
        title = request.POST.get(f'references-{i}-reference_title')
        surname = request.POST.get(f'references-{i}-reference_surname')
        
        if title and surname:
            reference_data.append({
                'index': i,
                'reference_title': title,
                'reference_surname': surname,
                'reference_names': request.POST.get(f'references-{i}-reference_names', ''),
                'reference_email': request.POST.get(f'references-{i}-reference_email', ''),
                'reference_phone': request.POST.get(f'references-{i}-reference_phone', ''),
                'reference_address': request.POST.get(f'references-{i}-reference_address', ''),
                'nature_of_relationship': request.POST.get(f'references-{i}-nature_of_relationship', ''),
                'letter_required': request.POST.get(f'references-{i}-letter_required') == 'on',
            })
    
    return reference_data

def validate_extracted_documents(document_data):
    """Validate extracted document data."""
    errors = []
    
    for doc in document_data:
        if not doc['category']:
            errors.append(f"Document {doc['index'] + 1}: Category is required")
        if not doc['title']:
            errors.append(f"Document {doc['index'] + 1}: Title is required")
        if not doc['file']:
            errors.append(f"Document {doc['index'] + 1}: File is required")
        elif doc['file'].size > 10 * 1024 * 1024:  # 10MB
            errors.append(f"Document {doc['index'] + 1}: File too large (max 10MB)")
    
    return len(errors) == 0, errors

def validate_extracted_references(reference_data):
    """Validate extracted reference data."""
    errors = []
    
    for ref in reference_data:
        if not ref['reference_title']:
            errors.append(f"Reference {ref['index'] + 1}: Title is required")
        if not ref['reference_surname']:
            errors.append(f"Reference {ref['index'] + 1}: Surname is required")
        if not ref['reference_email']:
            errors.append(f"Reference {ref['index'] + 1}: Email is required")
    
    return len(errors) == 0, errors

def save_extracted_documents(document_data, application, content_type, user):
    """Save documents manually."""
    saved_count = 0
    
    for doc_data in document_data:
        try:
            document = Document.objects.create(
                content_type=content_type,
                object_id=application.pk,
                category=doc_data['category'],
                title=doc_data['title'],
                description=doc_data['description'],
                file=doc_data['file'],
                is_required=doc_data['is_required'],
                uploaded_by=user if user.is_authenticated else None,
            )
            logger.info(f"Created document: {document.title} (ID: {document.pk})")
            saved_count += 1
        except Exception as e:
            logger.error(f"Error saving document {doc_data['title']}: {str(e)}")
    
    return saved_count

def save_extracted_references(reference_data, application, content_type):
    """Save references manually."""
    saved_count = 0
    
    for ref_data in reference_data:
        try:
            reference = Reference.objects.create(
                content_type=content_type,
                object_id=application.pk,
                reference_title=ref_data['reference_title'],
                reference_surname=ref_data['reference_surname'],
                reference_names=ref_data['reference_names'],
                reference_email=ref_data['reference_email'],
                reference_phone=ref_data['reference_phone'],
                reference_address=ref_data['reference_address'],
                nature_of_relationship=ref_data['nature_of_relationship'],
                letter_required=ref_data['letter_required'],
            )
            logger.info(f"Created reference: {reference.get_reference_full_name()} (ID: {reference.pk})")
            saved_count += 1
        except Exception as e:
            logger.error(f"Error saving reference {ref_data['reference_surname']}: {str(e)}")
    
    return saved_count


# Replace the mock formset functions in your views.py with these:

def create_mock_reference_formset():
    """Create a mock formset for template rendering."""
    class MockForm:
        def __init__(self):
            self.errors = {}
    
    class MockFormset:
        def __init__(self):
            self.management_form = self.MockManagementForm()
            self.forms = []  # Empty list so template can iterate
            self.errors = []
            self.non_form_errors = lambda: []
            
        # Make it iterable for the template
        def __iter__(self):
            return iter(self.forms)
        
        def __len__(self):
            return len(self.forms)
    
        class MockManagementForm:
            def __str__(self):
                return '''
                <input type="hidden" name="references-TOTAL_FORMS" value="0" id="id_references-TOTAL_FORMS">
                <input type="hidden" name="references-INITIAL_FORMS" value="0" id="id_references-INITIAL_FORMS">
                <input type="hidden" name="references-MIN_NUM_FORMS" value="0" id="id_references-MIN_NUM_FORMS">
                <input type="hidden" name="references-MAX_NUM_FORMS" value="1000" id="id_references-MAX_NUM_FORMS">
                '''
    
    return MockFormset()

def create_mock_document_formset():
    """Create a mock formset for template rendering."""
    class MockFormset:
        def __init__(self):
            self.management_form = self.MockManagementForm()
            self.forms = []  # Empty list so template can iterate
            self.errors = []
            self.non_form_errors = lambda: []
            
        # Make it iterable for the template
        def __iter__(self):
            return iter(self.forms)
            
        def __len__(self):
            return len(self.forms)
    
        class MockManagementForm:
            def __str__(self):
                return '''
                <input type="hidden" name="documents-TOTAL_FORMS" value="0" id="id_documents-TOTAL_FORMS">
                <input type="hidden" name="documents-INITIAL_FORMS" value="0" id="id_documents-INITIAL_FORMS">
                <input type="hidden" name="documents-MIN_NUM_FORMS" value="0" id="id_documents-MIN_NUM_FORMS">
                <input type="hidden" name="documents-MAX_NUM_FORMS" value="1000" id="id_documents-MAX_NUM_FORMS">
                '''
    
    return MockFormset()

# Add this new view for the success page
def application_success(request):
    """
    Success page after application submission.
    """
    success_data = request.session.get('application_success')
    
    if not success_data:
        # If no success data, redirect to onboarding start
        messages.info(request, "Please complete an application first.")
        return redirect('enrollments:onboarding_start')
    
    # Clear the success data from session after use
    del request.session['application_success']
    
    context = {
        'application_number': success_data.get('application_number'),
        'affiliation_type': success_data.get('affiliation_type'),
        'council_name': success_data.get('council_name'),
        'application_id': success_data.get('application_id'),
        'app_type': success_data.get('app_type'),
        'page_title': 'Application Submitted Successfully',
    }
    
    return render(request, 'enrollments/applications/success.html', context)
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
        
        # Initialize formsets based on application type
        formsets = {}
        if session.selected_affiliation_type.code == 'designated':
            # Only show formsets for designated applications
            formsets = {
                'qualifications': AcademicQualificationFormSet(request.POST, prefix='qualifications'),
                'experiences': PracticalExperienceFormSet(request.POST, prefix='experiences'),
                'references': ReferenceFormSet(request.POST, prefix='references'),
                'documents': DocumentFormSet(request.POST, request.FILES, prefix='documents'),
            }
        elif session.selected_affiliation_type.code in ['associated', 'student']:
            # For associated and student, only show references and documents
            formsets = {
                'references': ReferenceFormSet(request.POST, prefix='references'),
                'documents': DocumentFormSet(request.POST, request.FILES, prefix='documents'),
            }
        
        # Validate main form
        form_valid = form.is_valid()
        
        # Log form errors for debugging
        if not form_valid:
            logger.warning(f"Main form errors: {form.errors}")
            messages.error(request, "Please correct the main form errors.")
        
        # Validate formsets
        formsets_valid = True
        for formset_name, formset in formsets.items():
            if not formset.is_valid():
                formsets_valid = False
                logger.error(f"Formset {formset_name} validation failed: {formset.errors}")
                logger.error(f"Formset {formset_name} non-form errors: {formset.non_form_errors()}")
        
        if form_valid and formsets_valid:
            try:
                # Save main application first
                application = form.save(commit=False)
                application.onboarding_session = session
                
                # Set designation fields for designated applications
                if session.selected_affiliation_type.code == 'designated':
                    application.designation_category = session.selected_designation_category
                    application.designation_subcategory = session.selected_designation_subcategory
                
                application.save()
                
                # Get content type for this application
                content_type = ContentType.objects.get_for_model(application.__class__)
                
                # Save formsets with proper handling
                for formset_name, formset in formsets.items():
                    if formset_name in ['qualifications', 'experiences']:
                        # Direct foreign key relationship - standard inline formset
                        formset.instance = application
                        formset.save()
                    
                    elif formset_name in ['references', 'documents']:
                        # Generic foreign key relationship - manual handling
                        instances = formset.save(commit=False)
                        for instance in instances:
                            instance.content_type = content_type
                            instance.object_id = application.pk
                            instance.content_object = application
                            
                            # Set additional fields for documents
                            if formset_name == 'documents' and request.user.is_authenticated:
                                instance.uploaded_by = request.user
                            
                            instance.save()
                        
                        # Handle deleted instances
                        for obj in formset.deleted_objects:
                            obj.delete()
                
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
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                messages.error(request, "An error occurred while creating your application. Please try again.")
        
        else:
            # Form validation failed
            logger.warning(f"Application form validation failed")
            if not form_valid:
                logger.warning(f"Form errors: {form.errors}")
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
                'experiences': PracticalExperienceFormSet(prefix='experiences'),
                'references': ReferenceFormSet(prefix='references'),
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
    Comprehensive application detail view with admin review capabilities.
    """
    model_map = {
        'associated': AssociatedApplication,
        'designated': DesignatedApplication,
        'student': StudentApplication,
    }
    
    model = model_map.get(app_type)
    if not model:
        raise Http404("Invalid application type")
    
    # Get application with all related data
    if model == DesignatedApplication:
        application = get_object_or_404(
            model.objects.select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type',
                'designation_category',
                'designation_subcategory',
                'submitted_by',
                'reviewed_by',
                'approved_by'
            ).prefetch_related(
                'academic_qualifications',
                'practical_experiences',
                Prefetch(
                    'documents',
                    queryset=Document.objects.select_related('uploaded_by', 'verified_by')
                ),
                Prefetch(
                    'references',
                    queryset=Reference.objects.select_related().prefetch_related('documents')
                )
            ),
            pk=pk
        )
    else:
        application = get_object_or_404(
            model.objects.select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type',
                'submitted_by',
                'reviewed_by',
                'approved_by'
            ).prefetch_related(
                Prefetch(
                    'documents',
                    queryset=Document.objects.select_related('uploaded_by', 'verified_by')
                ),
                Prefetch(
                    'references',
                    queryset=Reference.objects.select_related().prefetch_related('documents')
                )
            ),
            pk=pk
        )
    
    # Check permissions
    user_can_view = (
        request.user.is_authenticated and (
            application.onboarding_session.user == request.user or
            application.email == request.user.email or
            is_admin_or_manager(request.user)
        )
    ) or not request.user.is_authenticated
    
    if not user_can_view:
        return HttpResponseForbidden("You don't have permission to view this application")
    
    # Determine user capabilities
    can_review = request.user.is_authenticated and can_approve_applications(request.user)
    can_edit = request.user.is_authenticated and (
        application.onboarding_session.user == request.user or
        is_admin_or_manager(request.user)
    )
    
    # Get review form for admins
    review_form = None
    if can_review and request.method == 'GET':
        review_form = ApplicationReviewForm(initial={
            'status': application.status,
            'reviewer_notes': application.reviewer_notes,
            'rejection_reason': application.rejection_reason,
        })
    
    # Calculate completion percentage
    completion_percentage = calculate_application_completion(application, app_type)
    
    # Get status timeline
    status_timeline = get_application_timeline(application)
    
    # Group documents by category
    documents_by_category = {}
    for doc in application.documents.all():
        category = doc.get_category_display()
        if category not in documents_by_category:
            documents_by_category[category] = []
        documents_by_category[category].append(doc)
    
    # Calculate document statistics
    total_documents = application.documents.count()
    verified_documents = application.documents.filter(verified=True).count()
    pending_documents = total_documents - verified_documents
    
    # Calculate reference statistics
    total_references = application.references.count()
    references_with_letters = application.references.filter(letter_received=True).count()
    pending_references = total_references - references_with_letters
    
    context = {
        'application': application,
        'app_type': app_type,
        'council': application.onboarding_session.selected_council,
        'affiliation_type': application.onboarding_session.selected_affiliation_type,
        'can_review': can_review,
        'can_edit': can_edit,
        'review_form': review_form,
        'completion_percentage': completion_percentage,
        'status_timeline': status_timeline,
        'documents_by_category': documents_by_category,
        'document_stats': {
            'total': total_documents,
            'verified': verified_documents,
            'pending': pending_documents,
        },
        'reference_stats': {
            'total': total_references,
            'with_letters': references_with_letters,
            'pending': pending_references,
        },
        'page_title': f'{app_type.title()} Application - {application.application_number}',
    }
    
    return render(request, 'enrollments/applications/detail.html', context)



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
# APPLICATION BULK ACTIONS
# ============================================================================

@login_required
@user_passes_test(can_approve_applications, login_url='/', redirect_field_name=None)
@require_POST
def application_bulk_action(request):
    """Handle bulk actions on applications"""
    action = request.POST.get('action')
    application_ids = request.POST.getlist('application_ids')
    
    if not action or not application_ids:
        messages.error(request, "No action or applications selected.")
        return redirect('enrollments:application_list')
    
    count = 0
    
    try:
        with transaction.atomic():
            for app_id in application_ids:
                # Get app_type and model
                for app_type, model in [('associated', AssociatedApplication), 
                                      ('designated', DesignatedApplication), 
                                      ('student', StudentApplication)]:
                    try:
                        app = model.objects.get(pk=app_id)
                        
                        if action == 'approve':
                            app.status = 'approved'
                            app.approved_at = timezone.now()
                            app.approved_by = request.user
                        elif action == 'reject':
                            app.status = 'rejected'
                            app.rejected_at = timezone.now()
                            app.rejected_by = request.user
                        elif action == 'under_review':
                            app.status = 'under_review'
                            app.reviewed_at = timezone.now()
                            app.reviewed_by = request.user
                        
                        app.save()
                        count += 1
                        break
                    except model.DoesNotExist:
                        continue
        
        messages.success(request, f'Successfully {action}d {count} applications.')
        
    except Exception as e:
        logger.error(f"Error in bulk action: {str(e)}")
        messages.error(request, "An error occurred during bulk action.")
    
    return redirect('enrollments:application_list')


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_application_completion(application, app_type):
    """Calculate application completion percentage"""
    total_fields = 0
    completed_fields = 0
    
    # Count basic required fields
    required_basic_fields = [
        'title', 'surname', 'full_names', 'email', 'cell_phone',
        'postal_address_line1', 'postal_city', 'postal_province',
        'postal_code', 'home_language', 'current_occupation'
    ]
    
    for field in required_basic_fields:
        total_fields += 1
        if getattr(application, field, None):
            completed_fields += 1
    
    # Count documents
    if application.documents.exists():
        completed_fields += 1
    total_fields += 1
    
    # Count references
    if application.references.exists():
        completed_fields += 1
    total_fields += 1
    
    # Count legal agreements
    legal_fields = ['popi_act_accepted', 'terms_accepted', 'information_accurate', 'declaration_accepted']
    for field in legal_fields:
        total_fields += 1
        if getattr(application, field, False):
            completed_fields += 1
    
    # Add type-specific fields
    if app_type == 'designated':
        if hasattr(application, 'academic_qualifications') and application.academic_qualifications.exists():
            completed_fields += 1
        total_fields += 1
        
        if hasattr(application, 'practical_experiences') and application.practical_experiences.exists():
            completed_fields += 1
        total_fields += 1
    
    elif app_type == 'student':
        student_fields = ['current_institution', 'course_of_study', 'expected_graduation']
        for field in student_fields:
            total_fields += 1
            if getattr(application, field, None):
                completed_fields += 1
    
    return int((completed_fields / total_fields) * 100) if total_fields > 0 else 0


def get_application_timeline(application):
    """Get application status timeline"""
    timeline = []
    
    # Created
    timeline.append({
        'status': 'Created',
        'date': application.created_at,
        'user': application.submitted_by,
        'icon': 'plus-circle',
        'color': 'primary'
    })
    
    # Submitted
    if application.submitted_at:
        timeline.append({
            'status': 'Submitted',
            'date': application.submitted_at,
            'user': application.submitted_by,
            'icon': 'check-circle',
            'color': 'info'
        })
    
    # Under Review
    if application.reviewed_at:
        timeline.append({
            'status': 'Under Review',
            'date': application.reviewed_at,
            'user': application.reviewed_by,
            'icon': 'eye',
            'color': 'warning'
        })
    
    # Approved/Rejected
    if application.approved_at:
        timeline.append({
            'status': 'Approved',
            'date': application.approved_at,
            'user': application.approved_by,
            'icon': 'check-circle-fill',
            'color': 'success'
        })
    elif application.rejected_at:
        timeline.append({
            'status': 'Rejected',
            'date': application.rejected_at,
            'user': application.rejected_by,
            'icon': 'x-circle-fill',
            'color': 'danger'
        })
    
    return timeline


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
def enrollment_dashboard_ajax(request):
    """Handle AJAX requests for dashboard updates"""
    # This would contain the same logic as above but return JSON
    # For now, return a simple response
    return JsonResponse({
        'status': 'success',
        'message': 'Dashboard data updated'
    })



@login_required
@user_passes_test(is_admin_or_manager, login_url='/', redirect_field_name=None)
def enrollment_dashboard(request):
    """
    Enhanced administrative dashboard with comprehensive statistics.
    Supports AJAX requests for real-time updates.
    """
    # Handle AJAX requests
    if request.GET.get('ajax') == '1':
        return enrollment_dashboard_ajax(request)
    
    # Initialize stats structure for all councils
    stats = {
        'cgmp': {'total': 0, 'approved': 0, 'pending': 0, 'by_type': {}},
        'cpsc': {'total': 0, 'approved': 0, 'pending': 0, 'by_type': {}},
        'cmtp': {'total': 0, 'approved': 0, 'pending': 0, 'by_type': {}},
    }
    
    # Get all councils
    councils = Council.objects.filter(is_active=True)
    council_map = {council.code.lower(): council for council in councils}
    
    # Calculate statistics for each council
    for council in councils:
        council_code = council.code.lower()
        council_stats = {
            'total': 0,
            'approved': 0,
            'pending': 0,
            'rejected': 0,
            'under_review': 0,
            'by_type': {}
        }
        
        # Get applications for this council across all types
        app_models = [
            ('associated', AssociatedApplication),
            ('designated', DesignatedApplication),
            ('student', StudentApplication)
        ]
        
        for app_type_name, app_model in app_models:
            apps = app_model.objects.filter(
                onboarding_session__selected_council=council
            )
            
            type_stats = {
                'total': apps.count(),
                'approved': apps.filter(status='approved').count(),
                'pending': apps.filter(status__in=['draft', 'submitted']).count(),
                'under_review': apps.filter(status='under_review').count(),
                'rejected': apps.filter(status='rejected').count(),
                'requires_clarification': apps.filter(status='requires_clarification').count(),
            }
            
            council_stats['by_type'][app_type_name] = type_stats
            council_stats['total'] += type_stats['total']
            council_stats['approved'] += type_stats['approved']
            council_stats['pending'] += type_stats['pending'] + type_stats['under_review']
            council_stats['rejected'] += type_stats['rejected']
            council_stats['under_review'] += type_stats['under_review']
        
        stats[council_code] = council_stats
    
    # Get recent applications across all types (last 20)
    recent_applications = []
    
    for app_type_name, app_model in app_models:
        apps = app_model.objects.select_related(
            'onboarding_session__selected_council',
            'onboarding_session__selected_affiliation_type'
        ).order_by('-created_at')[:15]
        
        for app in apps:
            app_data = {
                'id': app.pk,
                'type': app_type_name.title(),
                'council': app.onboarding_session.selected_council.code,
                'name': app.get_display_name(),
                'email': app.email,
                'application_number': app.application_number,
                'status': app.status,
                'created_at': app.created_at,
                'submitted_at': app.submitted_at,
            }
            
            # Add type-specific fields
            if app_type_name == 'designated' and hasattr(app, 'designation_category'):
                app_data['category'] = app.designation_category.name if app.designation_category else None
            elif app_type_name == 'student' and hasattr(app, 'current_institution'):
                app_data['institution'] = app.current_institution
            
            recent_applications.append(app_data)
    
    # Sort by creation date and limit to 20
    recent_applications.sort(key=lambda x: x['created_at'], reverse=True)
    recent_applications = recent_applications[:20]
    
    context = {
        'stats': stats,
        'recent_applications': recent_applications,
        'page_title': 'Enrollment Dashboard',
        'councils': council_map,
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
    

    