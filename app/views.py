import json
import logging
from datetime import timedelta, datetime
from decimal import Decimal
from typing import Dict, List, Any
from django.db.models import (
    Count, Sum, Q, Avg, F, Prefetch, Case, When, 
    IntegerField, DecimalField, DateField
)
from django.db.models.functions import Round
from django import forms
from django.http import (
    HttpResponseForbidden, JsonResponse, HttpResponse, 
    HttpResponseBadRequest, Http404
)
from django.utils import timezone
from datetime import timedelta
from app.notification_utils import create_notification, notify_users
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.db import transaction, models
from django.db.models import (
    Count, Sum, Q, Avg, F, Prefetch, Case, When, 
    IntegerField, DecimalField, DateField
)
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string

from app.forms import *
from .models import *
from .utils import (
    log_activity, send_notification, check_permission,
    get_user_workload, calculate_project_health, generate_activity_feed
)
from django.views.decorators.http import require_http_methods
from .notification_utils import (
    get_unread_count,
    mark_notification_read, 
    mark_all_read, 
    delete_notification,
    get_recent_notifications
)

User = get_user_model()
logger = logging.getLogger(__name__)


### ========== UTILITY DECORATORS AND FUNCTIONS ========== ###

def permission_required_or_owner(permission, model_class, pk_field='pk'):
    """
    Custom decorator that checks if user has permission OR is the owner of the object.
    Provides more flexible access control for workspace operations.
    """
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # Check if user has global permission
            if request.user.has_perm(permission):
                return view_func(request, *args, **kwargs)
            
            # Check if user is owner/creator of the object
            try:
                obj_pk = kwargs.get(pk_field)
                obj = get_object_or_404(model_class, pk=obj_pk)
                
                # Check various ownership patterns
                if hasattr(obj, 'created_by') and obj.created_by == request.user:
                    return view_func(request, *args, **kwargs)
                elif hasattr(obj, 'manager') and obj.manager == request.user:
                    return view_func(request, *args, **kwargs)
                elif hasattr(obj, 'assigned_to') and obj.assigned_to == request.user:
                    return view_func(request, *args, **kwargs)
                elif hasattr(obj, 'team_members') and request.user in obj.team_members.all():
                    return view_func(request, *args, **kwargs)
                    
            except Exception as e:
                logger.warning(f"Permission check failed: {e}")
                
            return HttpResponseForbidden("You don't have permission to access this resource.")
        return _wrapped_view
    return decorator


def rate_limit(key_prefix, max_requests=60, window_seconds=3600):
    """
    Simple rate limiting decorator using Django cache.
    Prevents abuse of API endpoints and resource-intensive operations.
    """
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # Create unique key for this user/IP
            user_id = request.user.id if request.user.is_authenticated else 'anonymous'
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            cache_key = f"rate_limit:{key_prefix}:{user_id}:{ip}"
            
            # Get current request count
            current_requests = cache.get(cache_key, 0)
            
            if current_requests >= max_requests:
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please try again later.'
                }, status=429)
            
            # Increment counter
            cache.set(cache_key, current_requests + 1, window_seconds)
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['title', 'description', 'resource_type', 'file', 'url']

class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ['resource']

        
def workspace_analytics(request):
    """
    Helper function to gather comprehensive workspace analytics.
    Used by dashboard and reporting views for consistent metrics.
    """
    cache_key = f"workspace_analytics_{request.user.id}"
    analytics = cache.get(cache_key)
    
    if analytics is None:
        # User-specific analytics
        user_tasks = Task.objects.filter(assigned_to=request.user, is_active=True)
        user_projects = Projects.objects.filter(
            Q(manager=request.user) | Q(team_members=request.user),
            is_active=True
        ).distinct()
        
        # Performance metrics
        completed_tasks_this_month = user_tasks.filter(
            completed_date__month=timezone.now().month,
            status__is_final=True
        ).count()
        
        overdue_tasks = user_tasks.filter(
            due_date__lt=timezone.now().date(),
            status__is_final=False
        ).count()
        
        # Workload analysis
        upcoming_deadlines = user_tasks.filter(
            due_date__lte=timezone.now().date() + timedelta(days=7),
            status__is_final=False
        ).order_by('due_date')[:5]
        
        # Time tracking
        this_week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        time_this_week = TimeEntry.objects.filter(
            user=request.user,
            start_time__date__gte=this_week_start
        ).aggregate(total=Sum('duration_minutes'))['total'] or 0
        
        analytics = {
            'active_tasks': user_tasks.count(),
            'active_projects': user_projects.count(),
            'completed_this_month': completed_tasks_this_month,
            'overdue_tasks': overdue_tasks,
            'upcoming_deadlines': list(upcoming_deadlines),
            'time_this_week': round(time_this_week / 60, 1),  # Convert to hours
            'projects_managed': user_projects.filter(manager=request.user).count(),
        }
        
        # Cache for 15 minutes
        cache.set(cache_key, analytics, 900)
    
    return analytics


### ========== DASHBOARD AND WORKSPACE OVERVIEW ========== ###

@login_required
def dashboard(request):
    """
    Main dashboard entry point - routes to appropriate dashboard based on user role.
    
    Routes:
    - LEARNER role -> Student-focused dashboard with learning progress
    - All other roles -> Admin/Staff dashboard with system management
    """
    user = request.user
    
    # Check if user is a learner - route to student dashboard
    if hasattr(user, 'acrp_role') and user.acrp_role == User.ACRPRole.LEARNER:
        return learner_dashboard(request)
    
    # Otherwise, show the admin/staff dashboard
    # ============================================================================
    # SYSTEM-WIDE STATISTICS
    # ============================================================================
    
    stats = {}
    
    # Enrollment Statistics
    try:
        from enrollments.models import AssociatedApplication, DesignatedApplication, StudentApplication
        
        # Get all applications across types
        all_applications = []
        for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
            all_applications.extend(model.objects.all())
        
        stats['total_applications'] = len(all_applications)
        stats['pending_applications'] = len([app for app in all_applications if app.status in ['submitted', 'under_review']])
        stats['approved_applications'] = len([app for app in all_applications if app.status == 'approved'])
        
    except ImportError:
        stats['total_applications'] = 0
        stats['pending_applications'] = 0
        stats['approved_applications'] = 0
    
    # Digital Card Statistics
    try:
        from affiliationcard.models import AffiliationCard
        
        stats['total_cards'] = AffiliationCard.objects.count()
        stats['active_cards'] = AffiliationCard.objects.filter(status='active').count()
        stats['expiring_cards'] = AffiliationCard.objects.filter(
            date_expires__lte=timezone.now().date() + timedelta(days=30),
            status='active'
        ).count()
        
    except ImportError:
        stats['total_cards'] = 0
        stats['active_cards'] = 0
        stats['expiring_cards'] = 0
    
    # CPD Statistics
    try:
        from cpd.models import CPDRecord, CPDApproval
        
        current_year = timezone.now().year
        
        # Get completed CPD records for current year with approved status
        approved_records = CPDRecord.objects.filter(
            user=user,
            completion_date__year=current_year,
            status='COMPLETED'
        ).filter(
            approval__status='APPROVED'
        )
        
        # Calculate total hours
        total_hours = 0
        for record in approved_records:
            total_hours += float(record.hours_awarded or record.hours_claimed or 0)
        
        stats['cpd_hours'] = total_hours
        
    except (ImportError, AttributeError):
        stats['cpd_hours'] = 0
    
    # Active Members
    stats['active_members'] = stats['active_cards'] or stats['approved_applications']
    stats['new_members'] = 0
    
    # ============================================================================
    # CORE CONTENT
    # ============================================================================
    
    # Urgent announcements
    announcements = Announcement.objects.filter(is_urgent=True).order_by('-published_at')[:5]
    
    # Mandatory events
    events = Event.objects.filter(is_public=True, start_time__gte=timezone.now()).order_by('start_time')[:5]
    
    # User's projects
    projects = Projects.objects.filter(
        manager=user
    ).order_by('-start_date')[:5]
    
    # ============================================================================
    # ITEMS REQUIRING ATTENTION
    # ============================================================================
    
    pending_items = []
    
    # Add role-based pending items for staff
    if user.is_staff or hasattr(user, 'role'):
        # Applications needing review
        try:
            pending_apps = []
            for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                pending_apps.extend(
                    model.objects.filter(status='submitted').values(
                        'id', 'application_number', 'full_names', 'created_at'
                    )[:3]
                )
            
            for app in pending_apps:
                pending_items.append({
                    'type': 'application',
                    'title': f"Review Application {app['application_number']}",
                    'description': f"Application from {app['full_names']} needs review",
                    'created': app['created_at'],
                    'url': f"/enrollments/applications/",
                })
        except:
            pass
        
        # Cards needing attention
        try:
            expiring_cards = AffiliationCard.objects.filter(
                date_expires__lte=timezone.now().date() + timedelta(days=30),
                status='active'
            )[:3]
            
            for card in expiring_cards:
                pending_items.append({
                    'type': 'card',
                    'title': f"Card Expiring Soon",
                    'description': f"Card {card.card_number} expires {card.date_expires}",
                    'created': card.date_expires,
                    'url': f"/affiliationcard/admin/cards/{card.pk}/",
                })
        except:
            pass
    
    # ============================================================================
    # CONTEXT ASSEMBLY
    # ============================================================================
    
    context = {
        'announcements': announcements,
        'events': events,
        'projects': projects,
        'unread_notifications_count': get_unread_count(request.user),
        'recent_notifications': get_recent_notifications(request.user, limit=5),
        'stats': stats,
        'pending_items': pending_items,
        'user_role': getattr(getattr(user, 'role', None), 'title', 'Member') if hasattr(user, 'role') else 'Member',
        'is_admin': user.is_staff,
        'system_status': {
            'card_service': 'operational',
            'email_service': 'operational', 
            'verification_service': 'operational',
        }
    }
    
    return render(request, 'app/dashboard.html', context)

@login_required
def learner_dashboard(request):
    """
    Student-focused dashboard showing learning progress, courses, assignments,
    CPD tracking, and personalized learning resources.
    
    This dashboard is specifically designed for users with LEARNER role,
    providing a clean, focused interface for their educational journey.
    """
    user = request.user
    
    # ============================================================================
    # LEARNER PROFILE AND ENROLLMENT INFO
    # ============================================================================
    
    learner_profile = {
        'username': user.username,
        'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
        'email': user.email,
        'registration_number': getattr(user, 'employee_code', user.username),
        'phone': getattr(user, 'phone', 'Not provided'),
    }
    
    # Get learner's application information
    application_info = None
    try:
        from enrollments.models import AssociatedApplication, DesignatedApplication, StudentApplication
        from django.contrib.contenttypes.models import ContentType
        
        # Try to find application linked to this user's email or registration number
        # Applications use 'email' and 'registration_number' fields
        for model in [StudentApplication, AssociatedApplication, DesignatedApplication]:
            application = model.objects.filter(
                Q(email=user.email) | Q(registration_number=user.username)
            ).first()
            
            if application:
                application_info = {
                    'type': model.__name__.replace('Application', ''),
                    'number': application.application_number,
                    'status': application.get_status_display(),
                    'council': application.onboarding_session.selected_council.name,
                    'affiliation_type': application.onboarding_session.selected_affiliation_type.name,
                }
                break
    except Exception as e:
        logger.warning(f"Could not fetch application info for learner: {e}")
    
    # ============================================================================
    # DIGITAL CARD STATUS
    # ============================================================================
    
    digital_card = None
    try:
        from affiliationcard.models import AffiliationCard
        
        # Find card associated with this learner
        # Try multiple lookup strategies for maximum compatibility
        card_obj = None
        
        # Strategy 1: Look up by affiliate_email
        if not card_obj:
            card_obj = AffiliationCard.objects.filter(
                affiliate_email=user.email
            ).first()
        
        # Strategy 2: Look up by internal_id or affiliate_id_number
        if not card_obj:
            card_obj = AffiliationCard.objects.filter(
                Q(internal_id=user.username) | 
                Q(affiliate_id_number=getattr(user, 'employee_code', user.username))
            ).first()
        
        # Strategy 3: Look up through application relationship (most reliable)
        if not card_obj and application_info:
            # Get the actual application object we found earlier
            for model in [StudentApplication, AssociatedApplication, DesignatedApplication]:
                application = model.objects.filter(
                    Q(email=user.email) | Q(registration_number=user.username)
                ).first()
                if application:
                    card_obj = AffiliationCard.objects.filter(
                        application=application
                    ).first()
                    break
        
        if card_obj:
            # Calculate days until expiry
            days_until_expiry = None
            if card_obj.date_expires:
                days_until_expiry = (card_obj.date_expires - timezone.now().date()).days
            
            digital_card = {
                'card_number': card_obj.card_number,
                'status': card_obj.get_status_display(),
                'issue_date': card_obj.date_issued,
                'expiry_date': card_obj.date_expires,
                'days_until_expiry': days_until_expiry,
                'is_expiring_soon': days_until_expiry and days_until_expiry <= 30,
                'url': f'/affiliationcard/cards/{card_obj.pk}/',
            }
    except Exception as e:
        logger.warning(f"Could not fetch digital card for learner: {e}")
    
    # ============================================================================
    # CPD PROGRESS TRACKING
    # ============================================================================
    
    cpd_progress = {
        'current_year_hours': 0,
        'required_hours': 20,  # Standard annual requirement
        'completion_percentage': 0,
        'pending_hours': 0,
        'approved_hours': 0,
        'recent_activities': [],
    }
    
    try:
        from cpd.models import CPDRecord
        
        current_year = timezone.now().year
        
        # Get all CPD records for current year
        year_records = CPDRecord.objects.filter(
            user=user,
            completion_date__year=current_year
        )
        
        # Calculate approved hours
        approved_records = year_records.filter(
            status='COMPLETED',
            approval__status='APPROVED'
        )
        
        for record in approved_records:
            cpd_progress['approved_hours'] += float(record.hours_awarded or record.hours_claimed or 0)
        
        # Calculate pending hours
        pending_records = year_records.filter(
            status='COMPLETED',
            approval__status__in=['PENDING', 'UNDER_REVIEW']
        )
        
        for record in pending_records:
            cpd_progress['pending_hours'] += float(record.hours_claimed or 0)
        
        # Total current year hours
        cpd_progress['current_year_hours'] = cpd_progress['approved_hours']
        
        # Calculate completion percentage
        cpd_progress['completion_percentage'] = min(
            int((cpd_progress['current_year_hours'] / cpd_progress['required_hours']) * 100),
            100
        )
        
        # Get recent CPD activities (last 5)
        cpd_progress['recent_activities'] = year_records.order_by('-completion_date')[:5]
        
    except Exception as e:
        logger.warning(f"Could not fetch CPD progress for learner: {e}")
    
    # ============================================================================
    # LEARNING ACTIVITIES (COURSES, ASSIGNMENTS, ETC.)
    # ============================================================================
    
    learning_stats = {
        'courses_enrolled': 0,
        'courses_completed': 0,
        'assignments_pending': 0,
        'assignments_completed': 0,
        'current_grade_average': 0,
    }
    
    # Placeholder for future LMS integration
    # When you add courses/assignments modules, populate these stats
    
    # ============================================================================
    # UPCOMING EVENTS AND WORKSHOPS
    # ============================================================================
    
    upcoming_events = []
    try:
        upcoming_events = Event.objects.filter(
            start_time__gte=timezone.now(),
            start_time__lte=timezone.now() + timedelta(days=30),
            is_active=True
        ).order_by('start_time')[:5]
    except Exception as e:
        logger.warning(f"Could not fetch upcoming events: {e}")
    
    # ============================================================================
    # RECENT ANNOUNCEMENTS FOR LEARNERS
    # ============================================================================
    
    announcements = []
    try:
        announcements = Announcement.objects.filter(
            published_at__lte=timezone.now(),
            is_active=True
        ).order_by('-published_at')[:5]
    except Exception as e:
        logger.warning(f"Could not fetch announcements: {e}")
    
    # ============================================================================
    # ACTION ITEMS FOR LEARNER
    # ============================================================================
    
    action_items = []
    
    # Check if CPD hours are below requirement
    if cpd_progress['current_year_hours'] < cpd_progress['required_hours']:
        hours_needed = cpd_progress['required_hours'] - cpd_progress['current_year_hours']
        action_items.append({
            'type': 'cpd',
            'priority': 'high' if hours_needed > 10 else 'medium',
            'title': 'Complete CPD Points',
            'description': f'You need {hours_needed} more CPD points to meet annual requirements',
            'url': '/cpd/activities/',
            'icon': 'award',
        })
    
    # Check if digital card is expiring soon
    if digital_card and digital_card.get('is_expiring_soon'):
        action_items.append({
            'type': 'card',
            'priority': 'high',
            'title': 'Digital Card Expiring Soon',
            'description': f"Your card expires in {digital_card['days_until_expiry']} days",
            'url': digital_card['url'],
            'icon': 'credit-card',
        })
    
    # Check for pending assignments (when implemented)
    if learning_stats['assignments_pending'] > 0:
        action_items.append({
            'type': 'assignment',
            'priority': 'medium',
            'title': 'Pending Assignments',
            'description': f"You have {learning_stats['assignments_pending']} assignments to complete",
            'url': '/learning/assignments/',
            'icon': 'file-text',
        })
    
    # ============================================================================
    # QUICK LINKS FOR LEARNERS
    # ============================================================================
    
    quick_links = [
        {
            'title': 'Learn',
            'description': 'View enrolled courses',
            'url': '/learn/',
            'icon': 'book',
            'color': 'blue',
        },
        {
            'title': 'CPD Activities',
            'description': 'Browse CPD opportunities',
            'url': '/cpd/activities/',
            'icon': 'award',
            'color': 'purple',
        },
        {
            'title': 'My Digital Card',
            'description': 'View your affiliation card',
            'url': '/card/my-card/',
            'icon': 'credit-card',
            'color': 'green',
        },
        {
            'title': 'Events & Workshops',
            'description': 'Register for events',
            'url': '/app/events/',
            'icon': 'calendar',
            'color': 'indigo',
        },
    ]
    
    # ============================================================================
    # CONTEXT ASSEMBLY AND RENDER
    # ============================================================================
    
    context = {
        'learner_profile': learner_profile,
        'application_info': application_info,
        'digital_card': digital_card,
        'cpd_progress': cpd_progress,
        'learning_stats': learning_stats,
        'upcoming_events': upcoming_events,
        'announcements': announcements,
        'action_items': action_items,
        'quick_links': quick_links,
        'page_title': 'My Learning Dashboard',
        'current_year': timezone.now().year,
        'unread_notifications_count': get_unread_count(request.user),
        'recent_notifications': get_recent_notifications(request.user, limit=5),
    }
    
    return render(request, 'app/learner_dashboard.html', context)


@login_required
@cache_page(300)  # Cache for 5 minutes
def workspace_dashboard(request):
    """
    Comprehensive workspace dashboard with personalized analytics, activity feed,
    and quick access to important items. Optimized with strategic caching and
    database query optimization.
    """
    user = request.user
    
    # Get user analytics
    analytics = workspace_analytics(request)
    
    # ========== CRITICAL ITEMS REQUIRING ATTENTION ========== #
    user_tz = request.GET.get('timezone')
    # Overdue tasks
    import django.utils.timezone as dj_timezone
    from datetime import timedelta

    # use dj_timezone instead of timezone
    overdue_tasks = Task.objects.select_related('project', 'assigned_to').filter(
        assigned_to=user,
        due_date__lt=dj_timezone.now().date(),
        status__is_final=False,
        is_active=True
    ).order_by('due_date')[:5]
    
    today = dj_timezone.localdate()
    week_ahead = today + timedelta(days=7)
    from django.db.models import Q, Count, Case, When, F, DecimalField

    upcoming_deadlines = Task.objects.select_related('project').filter(
        assigned_to=user,
        due_date__lte=week_ahead,
        due_date__gte=today,
        status__is_final=False,
        is_active=True
    ).order_by('due_date')[:5]

    
    # Projects requiring attention (over budget, overdue, etc.)
    attention_projects = Projects.objects.select_related('manager', 'status').filter(
        Q(manager=user) | Q(team_members=user),
        is_active=True
    ).annotate(
        overdue_tasks_count=Count(
            'tasks',
            filter=Q(
                tasks__due_date__lt=dj_timezone.now().date(),
                tasks__status__is_final=False
            )
        ),
        budget_utilization=Case(
            When(budget_allocated__gt=0, 
                 then=F('budget_spent') * 100 / F('budget_allocated')),
            default=0,
            output_field=DecimalField(max_digits=5, decimal_places=2)
        )
    ).filter(
        Q(overdue_tasks_count__gt=0) | Q(budget_utilization__gt=80)
    )[:3]
    
    # ========== RECENT ACTIVITY AND COLLABORATION ========== #
    
    # Recent comments on user's projects/tasks
    user_projects_ids = list(Projects.objects.filter(
        Q(manager=user) | Q(team_members=user)
    ).values_list('id', flat=True))
    

    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q
    from django.utils import timezone
    from datetime import timedelta

    proj_ct = ContentType.objects.get_for_model(Projects)
    task_ct = ContentType.objects.get_for_model(Task)

    # collect task IDs that belong to the user's projects
    task_ids_qs = Task.objects.filter(project_id__in=user_projects_ids).values_list('id', flat=True)
    task_ids = [str(t) for t in task_ids_qs]  # object_id is a CharField, so use strings

    # make sure user_projects_ids are strings too (if they are UUIDs)
    project_ids = [str(p) for p in user_projects_ids]

    recent_comments = Comment.objects.select_related('author').filter(
        Q(content_type=proj_ct, object_id__in=project_ids) |
        Q(content_type=task_ct, object_id__in=task_ids),
        is_deleted=False,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-created_at')[:5]


    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone
    from datetime import timedelta

    proj_ct = ContentType.objects.get_for_model(Projects)
    task_ct = ContentType.objects.get_for_model(Task)

    # collect all Task IDs for the user’s projects
    task_ids = Task.objects.filter(
        project_id__in=user_projects_ids
    ).values_list('id', flat=True)

    recent_comments = Comment.objects.select_related('author').filter(
        Q(content_type=proj_ct, object_id__in=user_projects_ids) |
        Q(content_type=task_ct, object_id__in=task_ids),
        is_deleted=False,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-created_at')[:5]

    
    # ========== TEAM AND PROJECT INSIGHTS ========== #
    
    # Team performance metrics for managed projects
    team_metrics = {}
    if analytics['projects_managed'] > 0:
        managed_projects = Projects.objects.filter(manager=user, is_active=True)
        
        team_metrics = {
            'total_team_members': ProjectMembership.objects.filter(
                project__in=managed_projects,
                is_active=True
            ).count(),
            'team_completion_rate': Task.objects.filter(
                project__in=managed_projects,
                completed_date__month=timezone.now().month,
                status__is_final=True
            ).count(),
            'projects_on_track': managed_projects.filter(
                planned_end_date__gte=timezone.now().date()
            ).count(),
        }
    
    # ========== UPCOMING EVENTS AND MEETINGS ========== #
    
    upcoming_events = Event.objects.select_related('created_by').filter(
        Q(participants=user) | Q(is_public=True),
        start_time__gte=timezone.now(),
        start_time__lte=timezone.now() + timedelta(days=7),
        is_active=True
    ).order_by('start_time')[:5]
    
    # ========== RECENT ANNOUNCEMENTS ========== #
    
    # ========== NOTIFICATIONS AND ALERTS ========== #
    
    unread_notifications = Notification.objects.filter(
        recipient=user,
        is_read=False,
        is_active=True
    ).order_by('-created_at')[:5]
    
    # ========== QUICK ACTIONS AND SHORTCUTS ========== #
    
    quick_actions = []
    
    # Suggest creating tasks for overdue items
    if overdue_tasks.exists():
        quick_actions.append({
            'title': 'Review Overdue Tasks',
            'description': f'You have {overdue_tasks.count()} overdue tasks',
            'url': '/app/tasks/?filter=overdue',
            'priority': 'high',
            'icon': 'clock'
        })
    
    # Suggest time entry if none today
    today_time_entries = TimeEntry.objects.filter(
        user=user,
        start_time__date=timezone.now().date()
    ).exists()
    
    if not today_time_entries:
        quick_actions.append({
            'title': 'Log Time Today',
            'description': 'No time entries recorded for today',
            'url': '/app/time-tracking/add/',
            'priority': 'medium',
            'icon': 'timer'
        })
    
    # ========== PERFORMANCE INSIGHTS ========== #
    
    # Weekly productivity comparison
    last_week_start = timezone.now().date() - timedelta(days=timezone.now().weekday() + 7)
    last_week_end = last_week_start + timedelta(days=6)
    
    last_week_completed = Task.objects.filter(
        assigned_to=user,
        completed_date__date__range=[last_week_start, last_week_end],
        status__is_final=True
    ).count()
    
    productivity_trend = analytics['completed_this_month'] - last_week_completed
    
    context = {
        # Core analytics
        'analytics': analytics,
        'team_metrics': team_metrics,
        'productivity_trend': productivity_trend,
        
        # Critical items
        'overdue_tasks': overdue_tasks,
        'upcoming_deadlines': upcoming_deadlines,
        'attention_projects': attention_projects,
        
        # Communication and collaboration
        'recent_comments': recent_comments,
        'unread_notifications': unread_notifications,
        
        # Schedule and events
        'upcoming_events': upcoming_events,
        
        # Actions and insights
        'quick_actions': quick_actions,
        
        # System status
        'workspace_health': {
            'projects_on_track': len([p for p in attention_projects if p.overdue_tasks_count == 0]),
            'team_utilization': min(analytics['time_this_week'] / 40 * 100, 100),  # Assume 40h week
            'completion_rate': analytics['completed_this_month'],
        }
    }
    
    return render(request, 'app/workspace_dashboard.html', context)


### ========== ENHANCED KANBAN BOARD SYSTEM ========== ###

@login_required
@require_http_methods(["GET"])
def kanban_workspace(request):
    """
    Advanced kanban board showing all projects and tasks with filtering,
    sorting, and real-time collaboration features. Optimized for large datasets.
    """
    
    # ========== QUERY PARAMETER PROCESSING ========== #
    
    # Filtering options
    project_filter = request.GET.get('project')
    assignee_filter = request.GET.get('assignee')
    priority_filter = request.GET.get('priority')
    tag_filter = request.GET.get('tags')
    date_range = request.GET.get('date_range', '30')  # days
    view_mode = request.GET.get('view', 'all')  # all, my_tasks, my_projects
    
    # ========== BASE QUERYSET WITH PERMISSIONS ========== #
    
    # Get projects user has access to
    if view_mode == 'my_projects':
        base_projects = Projects.objects.filter(
            Q(manager=request.user) | Q(team_members=request.user),
            is_active=True
        ).distinct()
    elif view_mode == 'my_tasks':
        base_projects = Projects.objects.filter(
            tasks__assigned_to=request.user,
            is_active=True
        ).distinct()
    else:
        # All projects user can view
        base_projects = Projects.objects.filter(
            Q(is_public=True) | Q(manager=request.user) | Q(team_members=request.user),
            is_active=True
        ).distinct()
    
    # Apply project filter
    if project_filter:
        base_projects = base_projects.filter(id=project_filter)
    
    # ========== TASK QUERYSET WITH OPTIMIZATIONS ========== #
    
    tasks_query = Task.objects.select_related(
        'project', 'assigned_to', 'status', 'created_by'
    ).prefetch_related(
        'tags', 'dependencies'
    ).filter(
        project__in=base_projects,
        is_active=True
    )
    
    # Apply filters
    if assignee_filter:
        if assignee_filter == 'unassigned':
            tasks_query = tasks_query.filter(assigned_to__isnull=True)
        else:
            tasks_query = tasks_query.filter(assigned_to_id=assignee_filter)
    
    if priority_filter:
        tasks_query = tasks_query.filter(priority=priority_filter)
    
    if tag_filter:
        tag_list = tag_filter.split(',')
        tasks_query = tasks_query.filter(tags__name__in=tag_list)
    
    # Date range filter
    if date_range != 'all':
        date_threshold = timezone.now().date() + timedelta(days=int(date_range))
        tasks_query = tasks_query.filter(due_date__lte=date_threshold)
    
    # ========== KANBAN BOARD ORGANIZATION ========== #
    
    # Get all active task statuses for kanban columns
    kanban_statuses = TaskStatus.objects.filter(is_active=True).order_by('order')
    
    # Organize tasks by status
    kanban_columns = []
    for status in kanban_statuses:
        status_tasks = tasks_query.filter(status=status).annotate(
            dependency_count=Count('dependencies', filter=Q(dependencies__status__is_final=False))
        ).order_by('-priority', 'due_date')
        
        # Calculate column metrics
        total_tasks = status_tasks.count()
        overdue_count = status_tasks.filter(due_date__lt=timezone.now().date()).count()
        high_priority_count = status_tasks.filter(priority__lte=2).count()
        
        kanban_columns.append({
            'status': status,
            'tasks': status_tasks,
            'metrics': {
                'total': total_tasks,
                'overdue': overdue_count,
                'high_priority': high_priority_count,
            }
        })
    
    # ========== PROJECT SUMMARY CARDS ========== #
    
    project_summaries = base_projects.annotate(
        total_tasks=Count('tasks', filter=Q(tasks__is_active=True)),
        completed_tasks=Count('tasks', filter=Q(
            tasks__status__is_final=True,
            tasks__is_active=True
        )),
        overdue_tasks=Count('tasks', filter=Q(
            tasks__due_date__lt=timezone.now().date(),
            tasks__status__is_final=False,
            tasks__is_active=True
        )),
        team_size=Count('team_members', distinct=True)
    ).order_by('-updated_at')[:10]  # Limit to most recent projects
    
    # ========== FILTER OPTIONS FOR UI ========== #
    
    # Available assignees (users with tasks in visible projects)
    available_assignees = User.objects.filter(
        assigned_tasks__project__in=base_projects,
        assigned_tasks__is_active=True
    ).distinct().order_by('first_name', 'last_name')
    
    # Available tags
    available_tags = Tag.objects.filter(
        tasks__project__in=base_projects,
        tasks__is_active=True
    ).distinct().order_by('name')
    
    # Available projects for filtering
    filter_projects = base_projects.order_by('name')
    
    # ========== QUICK STATS FOR HEADER ========== #
    
    quick_stats = {
        'total_tasks': tasks_query.count(),
        'my_tasks': tasks_query.filter(assigned_to=request.user).count(),
        'overdue': tasks_query.filter(due_date__lt=timezone.now().date()).count(),
        'completed_today': tasks_query.filter(
            completed_date__date=timezone.now().date(),
            status__is_final=True
        ).count(),
    }
    
    # ========== COLLABORATION DATA ========== #
    
    # Recent activity on visible tasks
    recent_activity = ActivityLog.objects.select_related('user').filter(
        content_type=ContentType.objects.get_for_model(Task),
        object_id__in=tasks_query.values_list('id', flat=True),
        timestamp__gte=timezone.now() - timedelta(hours=24)
    ).order_by('-timestamp')[:10]
    
    context = {
        'kanban_columns': kanban_columns,
        'project_summaries': project_summaries,
        'quick_stats': quick_stats,
        'recent_activity': recent_activity,
        
        # Filter options
        'available_assignees': available_assignees,
        'available_tags': available_tags,
        'filter_projects': filter_projects,
        'priority_choices': Task.PRIORITY_LEVELS,
        
        # Current filters
        'current_filters': {
            'project': project_filter,
            'assignee': assignee_filter,
            'priority': priority_filter,
            'tags': tag_filter,
            'date_range': date_range,
            'view_mode': view_mode,
        },
        
        # UI configuration
        'kanban_config': {
            'enable_drag_drop': True,
            'auto_refresh': True,
            'show_avatars': True,
            'compact_mode': request.GET.get('compact') == 'true',
        }
    }
    
    return render(request, 'app/kanban_workspace.html', context)


@login_required
@require_POST
@rate_limit('kanban_update', max_requests=100, window_seconds=3600)
def kanban_update_task_status(request, task_id):
    """
    AJAX endpoint for updating task status via drag-and-drop in kanban board.
    Includes validation, permission checking, and activity logging.
    """
    try:
        with transaction.atomic():
            task = get_object_or_404(Task, id=task_id, is_active=True)
            
            # Permission check - user must be assignee, creator, or project team member
            if not (task.assigned_to == request.user or 
                    task.created_by == request.user or
                    request.user in task.project.team_members.all() or
                    task.project.manager == request.user or
                    request.user.has_perm('app.manage_tasks')):
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied'
                }, status=403)
            
            # Get new status from request
            data = json.loads(request.body)
            new_status_id = data.get('status_id')
            new_position = data.get('position', 0)
            
            new_status = get_object_or_404(TaskStatus, id=new_status_id, is_active=True)
            old_status = task.status
            
            # Validate status transition (optional business rule)
            # You can add custom validation logic here
            
            # Update task
            task.status = new_status
            
            # Auto-complete if moved to final status
            if new_status.is_final and not task.completed_date:
                task.completed_date = timezone.now()
                task.progress_percentage = 100.00
                
                # Log time entry if user has been working on it
                # (This could be expanded to track active work sessions)
            
            # Auto-start if moved from initial status
            if old_status.is_initial and not new_status.is_initial:
                if not task.start_date:
                    task.start_date = timezone.now().date()
            
            task.save()
            
            # Log activity
            log_activity(
                user=request.user,
                action_type='update',
                content_object=task,
                description=f"Moved task from '{old_status.name}' to '{new_status.name}'",
                extra_data={
                    'old_status': old_status.name,
                    'new_status': new_status.name,
                    'position': new_position
                }
            )
            
            # Send notifications if task is assigned to someone else
            if task.assigned_to and task.assigned_to != request.user:
                send_notification(
                    recipient=task.assigned_to,
                    notification_type='task_updated',
                    title=f'Task status updated: {task.title}',
                    message=f'{str(request.user)} moved your task to "{new_status.name}"',
                    content_object=task,
                    action_url=f'/tasks/{task.id}/'
                )
            
            # Calculate project progress update
            task.project.progress_percentage = task.project.get_completion_percentage()
            task.project.save(update_fields=['progress_percentage'])
            
            return JsonResponse({
                'success': True,
                'task': {
                    'id': str(task.id),
                    'title': task.title,
                    'status': new_status.name,
                    'status_color': new_status.color,
                    'completed_date': task.completed_date.isoformat() if task.completed_date else None,
                    'progress': float(task.progress_percentage),
                }
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating task status: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


### ========== ENHANCED PROJECT MANAGEMENT ========== ###

@login_required
def project_list(request):
    """
    Enhanced project list with advanced filtering, sorting, and analytics.
    Supports multiple view modes and export functionality.
    """
    
    # ========== QUERY PARAMETERS ========== #
    
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    manager_filter = request.GET.get('manager', '')
    date_filter = request.GET.get('date_filter', '')
    view_mode = request.GET.get('view', 'grid')  # grid, list, timeline
    sort_by = request.GET.get('sort', '-updated_at')
    
    # ========== BASE QUERYSET WITH PERMISSIONS ========== #
    
    projects = Projects.objects.select_related(
        'manager', 'status', 'created_by'
    ).prefetch_related(
        'team_members', 'tags', 'milestones'
    ).filter(
        Q(is_public=True) | Q(manager=request.user) | Q(team_members=request.user),
        is_active=True
    ).distinct()
    
    # ========== APPLY FILTERS ========== #
    
    if search_query:
        projects = projects.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(tags__name__icontains=search_query)
        ).distinct()
    
    if status_filter:
        projects = projects.filter(status_id=status_filter)
    
    if priority_filter:
        projects = projects.filter(priority=priority_filter)
    
    if manager_filter:
        if manager_filter == 'me':
            projects = projects.filter(manager=request.user)
        else:
            projects = projects.filter(manager_id=manager_filter)
    
    # Date filtering
    if date_filter == 'starting_soon':
        projects = projects.filter(
            start_date__gte=timezone.now().date(),
            start_date__lte=timezone.now().date() + timedelta(days=30)
        )
    elif date_filter == 'ending_soon':
        projects = projects.filter(
            planned_end_date__gte=timezone.now().date(),
            planned_end_date__lte=timezone.now().date() + timedelta(days=30)
        )
    elif date_filter == 'overdue':
        projects = projects.filter(
            planned_end_date__lt=timezone.now().date(),
            status__is_final=False
        )
    
    # ========== ANNOTATE WITH ANALYTICS ========== #
    
    projects = projects.annotate(
        total_tasks=Count('tasks', filter=Q(tasks__is_active=True)),
        completed_tasks=Count('tasks', filter=Q(
            tasks__status__is_final=True,
            tasks__is_active=True
        )),
        overdue_tasks=Count('tasks', filter=Q(
            tasks__due_date__lt=timezone.now().date(),
            tasks__status__is_final=False,
            tasks__is_active=True
        )),
        team_size=Count('team_members', distinct=True),
        total_time_logged=Sum('time_entries__duration_minutes'),
        budget_utilization=Case(
            When(budget_allocated__gt=0, 
                 then=F('budget_spent') * 100 / F('budget_allocated')),
            default=0,
            output_field=DecimalField(max_digits=5, decimal_places=2)
        ),
        completion_percentage=Case(
            When(total_tasks__gt=0,
                 then=F('completed_tasks') * 100 / F('total_tasks')),
            default=0,
            output_field=DecimalField(max_digits=5, decimal_places=2)
        )
    )
    
    # ========== SORTING ========== #
    
    valid_sort_fields = [
        'name', '-name', 'start_date', '-start_date', 'planned_end_date', 
        '-planned_end_date', 'priority', '-priority', 'completion_percentage',
        '-completion_percentage', 'updated_at', '-updated_at'
    ]
    
    if sort_by in valid_sort_fields:
        projects = projects.order_by(sort_by)
    else:
        projects = projects.order_by('-updated_at')
    
    # ========== PAGINATION ========== #
    
    paginator = Paginator(projects, 12)  # 12 projects per page
    page = request.GET.get('page')
    
    try:
        projects_page = paginator.page(page)
    except PageNotAnInteger:
        projects_page = paginator.page(1)
    except EmptyPage:
        projects_page = paginator.page(paginator.num_pages)
    
    # ========== FILTER OPTIONS ========== #
    
    # Available project managers
    available_managers = User.objects.filter(
        managed_projects__isnull=False,
        managed_projects__is_active=True
    ).distinct().order_by('first_name', 'last_name')
    
    # Available statuses
    available_statuses = ProjectStatus.objects.filter(is_active=True).order_by('order')
    
    # ========== DASHBOARD METRICS ========== #
    
    dashboard_metrics = {
        'total_projects': projects.count(),
        'my_projects': projects.filter(manager=request.user).count(),
        'active_projects': projects.filter(status__is_final=False).count(),
        'overdue_projects': projects.filter(
            planned_end_date__lt=timezone.now().date(),
            status__is_final=False
        ).count(),
    }
    
    context = {
        'projects': projects_page,
        'dashboard_metrics': dashboard_metrics,
        'available_managers': available_managers,
        'available_statuses': available_statuses,
        'priority_choices': Projects.PRIORITY_LEVELS,
        'current_filters': {
            'search': search_query,
            'status': status_filter,
            'priority': priority_filter,
            'manager': manager_filter,
            'date_filter': date_filter,
            'view_mode': view_mode,
            'sort': sort_by,
        },
        'view_mode': view_mode,
    }
    
    return render(request, 'app/project_list.html', context)


@login_required
@permission_required_or_owner('app.manage_projects', Projects)
def project_detail(request, pk):
    """
    Comprehensive project detail view with team collaboration, timeline,
    and real-time updates. Includes all project-related information.
    """
    
    # ========== FETCH PROJECT WITH OPTIMIZATIONS ========== #
    
    project = get_object_or_404(
        Projects.objects.select_related(
            'manager', 'status', 'created_by'
        ).prefetch_related(
            'team_members', 'tags', 'milestones', 'tasks__assigned_to',
            'tasks__status'
        ),
        pk=pk,
        is_active=True
    )
    
    # Permission check
    if not (project.is_public or 
            project.manager == request.user or
            request.user in project.team_members.all() or
            request.user.has_perm('app.view_all_projects')):
        return HttpResponseForbidden("You don't have permission to view this project.")
    
    # ========== PROJECT ANALYTICS ========== #
    
    # Task analytics
    task_analytics = {
        'total': project.tasks.filter(is_active=True).count(),
        'completed': project.tasks.filter(status__is_final=True, is_active=True).count(),
        'in_progress': project.tasks.filter(status__is_final=False, is_active=True).count(),
        'overdue': project.tasks.filter(
            due_date__lt=timezone.now().date(),
            status__is_final=False,
            is_active=True
        ).count(),
        'high_priority': project.tasks.filter(priority__lte=2, is_active=True).count(),
    }
    
    # Time tracking analytics
    time_analytics = project.time_entries.aggregate(
        total_hours=Sum('duration_minutes'),
        billable_hours=Sum('duration_minutes', filter=Q(is_billable=True)),
        this_week_hours=Sum(
            'duration_minutes',
            filter=Q(start_time__week=timezone.now().isocalendar()[1])
        )
    )
    
    # Convert minutes to hours
    for key, value in time_analytics.items():
        time_analytics[key] = round((value or 0) / 60, 1)
    
    # Budget analytics
    budget_analytics = {
        'allocated': project.budget_allocated or 0,
        'spent': project.budget_spent or 0,
        'remaining': (project.budget_allocated or 0) - (project.budget_spent or 0),
        'utilization_percentage': project.get_budget_utilization(),
    }
    
    # Timeline analytics
    total_days = (project.planned_end_date - project.start_date).days
    elapsed_days = (timezone.now().date() - project.start_date).days
    timeline_progress = min((elapsed_days / total_days * 100) if total_days > 0 else 0, 100)
    
    # ========== TASK BREAKDOWN BY STATUS ========== #
    
    task_statuses = TaskStatus.objects.filter(is_active=True).order_by('order')
    tasks_by_status = []
    
    for status in task_statuses:
        status_tasks = project.tasks.filter(
            status=status, 
            is_active=True
        ).select_related('assigned_to').order_by('-priority', 'due_date')
        
        tasks_by_status.append({
            'status': status,
            'tasks': status_tasks,
            'count': status_tasks.count()
        })
    
    # ========== MILESTONES AND TIMELINE ========== #
    
    milestones = project.milestones.filter(is_active=True).order_by('planned_date')
    
    # Upcoming milestones
    upcoming_milestones = milestones.filter(
        planned_date__gte=timezone.now().date(),
        is_completed=False
    )[:3]
    
    # ========== TEAM INFORMATION ========== #
    
    team_members = ProjectMembership.objects.select_related('user').filter(
        project=project,
        is_active=True
    ).order_by('role', 'joined_at')
    
    # Team workload analysis
    team_workload = {}
    for membership in team_members:
        user = membership.user
        user_tasks = project.tasks.filter(assigned_to=user, is_active=True)
        
        team_workload[user.id] = {
            'user': user,
            'role': membership.get_role_display(),
            'total_tasks': user_tasks.count(),
            'completed_tasks': user_tasks.filter(status__is_final=True).count(),
            'overdue_tasks': user_tasks.filter(
                due_date__lt=timezone.now().date(),
                status__is_final=False
            ).count(),
            'this_week_hours': user.time_entries.filter(
                project=project,
                start_time__week=timezone.now().isocalendar()[1]
            ).aggregate(
                total=Sum('duration_minutes')
            )['total'] or 0
        }
        
        # Convert minutes to hours
        team_workload[user.id]['this_week_hours'] = round(
            team_workload[user.id]['this_week_hours'] / 60, 1
        )
    
    # ========== RECENT ACTIVITY ========== #
    
    recent_activity = ActivityLog.objects.select_related('user').filter(
        Q(related_project=project) |
        Q(content_type=ContentType.objects.get_for_model(Projects), object_id=str(project.id)),
        timestamp__gte=timezone.now() - timedelta(days=14)
    ).order_by('-timestamp')[:15]
    
    # ========== COMMENTS AND COLLABORATION ========== #
    
    project_comments = Comment.objects.select_related('author').filter(
        content_type=ContentType.objects.get_for_model(Projects),
        object_id=str(project.id),
        is_deleted=False
    ).order_by('-created_at')[:10]
    
    # ========== PROJECT HEALTH SCORE ========== #
    
    health_metrics = {
        'schedule': 100 - min((timeline_progress - (task_analytics.get('completed', 0) / max(task_analytics.get('total', 1), 1) * 100)), 100),
        'budget': 100 - min(budget_analytics['utilization_percentage'], 100) if budget_analytics['allocated'] > 0 else 100,
        'quality': 100 - (task_analytics.get('overdue', 0) / max(task_analytics.get('total', 1), 1) * 100),
        'team': min(len(team_workload) / max(max(task_analytics.get('total', 1), 1) / 5, 1) * 100, 100),
    }
    
    overall_health = sum(float(value) for value in health_metrics.values()) / len(health_metrics)
    health_stroke_value = round(float(overall_health) * 1.76, 2)

    
    # ========== CONTEXT ASSEMBLY ========== #
    
    context = {
        'project': project,
        'task_analytics': task_analytics,
        'time_analytics': time_analytics,
        'budget_analytics': budget_analytics,
        'timeline_progress': timeline_progress,
        'tasks_by_status': tasks_by_status,
        'milestones': milestones,
        'upcoming_milestones': upcoming_milestones,
        'team_members': team_members,
        'team_workload': team_workload,
        'recent_activity': recent_activity,
        'project_comments': project_comments,
        'health_metrics': health_metrics,
        'overall_health': overall_health,
        'health_stroke_value': health_stroke_value,
        
        # User permissions
        'can_edit': (
            project.manager == request.user or
            request.user.has_perm('app.manage_projects')
        ),
        'can_manage_team': (
            project.manager == request.user or
            request.user.has_perm('app.manage_projects') or
            team_members.filter(
                user=request.user,
                can_invite_members=True
            ).exists()
        ),
        'can_manage_tasks': (
            project.manager == request.user or
            request.user in project.team_members.all() or
            request.user.has_perm('app.manage_tasks')
        ),
        
        # Forms for quick actions
        'comment_form': CommentForm(),
        'task_form': TaskForm(initial={'project': project.id}),
    }
    
    return render(request, 'app/project_detail.html', context)


### ========== ENHANCED TASK MANAGEMENT ========== ###

@login_required
@require_POST
def task_create_ajax(request):
    """
    Bulletproof AJAX endpoint for creating tasks with maximum error handling.
    """
    try:
        with transaction.atomic():
            data = json.loads(request.body)
            logger.info(f"Starting task creation with data: {data}")
            
            # Validate required fields
            required_fields = ['title', 'project_id', 'due_date']
            for field in required_fields:
                if not data.get(field):
                    return JsonResponse({
                        'success': False,
                        'error': f'Field {field} is required'
                    }, status=400)
            
            # Validate project access
            project = get_object_or_404(Projects, id=data['project_id'], is_active=True)
            
            if not (project.manager == request.user or
                    request.user in project.team_members.all() or
                    request.user.has_perm('app.manage_tasks')):
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied'
                }, status=403)
            
            # Create task
            task = Task(
                title=data['title'],
                description=data.get('description', ''),
                project=project,
                due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date(),
                priority=int(data.get('priority', 3)),
                created_by=request.user,
                task_type=data.get('task_type', 'task')
            )
            
            # Handle assignment
            if data.get('assigned_to_id'):
                try:
                    assigned_user = User.objects.get(id=data['assigned_to_id'])
                    if (assigned_user in project.team_members.all() or 
                        assigned_user == project.manager):
                        task.assigned_to = assigned_user
                except User.DoesNotExist:
                    pass  # Skip assignment if user not found
            
            # Set initial status
            try:
                initial_status = TaskStatus.objects.filter(is_initial=True, is_active=True).first()
                if initial_status:
                    task.status = initial_status
            except:
                pass  # Continue without status if TaskStatus model has issues
            
            # Handle estimated hours
            if data.get('estimated_hours'):
                try:
                    task.estimated_hours = float(data['estimated_hours'])
                except ValueError:
                    pass  # Continue without estimated hours if invalid
            
            task.save()
            logger.info(f"Task saved successfully: {task.id}")
            
            # Handle tags
            if data.get('tags'):
                try:
                    tag_names = [tag.strip() for tag in data['tags'].split(',') if tag.strip()]
                    for tag_name in tag_names:
                        tag, created = Tag.objects.get_or_create(name=tag_name)
                        task.tags.add(tag)
                except Exception as e:
                    logger.warning(f"Failed to add tags: {e}")
            
            # Build response with maximum safety
            response_data = {
                'success': True,
                'task': {
                    'id': str(task.id),
                    'title': str(task.title),
                    'description': str(task.description),
                    'due_date': task.due_date.isoformat(),
                    'priority': int(task.priority),
                    'url': f'/tasks/{task.id}/',
                    'created_at': task.created_at.isoformat(),
                }
            }
            
            # Safely get project info
            try:
                response_data['task']['project_name'] = str(project.name)
                response_data['task']['project_id'] = str(project.id)
            except Exception as e:
                logger.warning(f"Error getting project info: {e}")
                response_data['task']['project_name'] = 'Unknown Project'
                response_data['task']['project_id'] = str(data['project_id'])
            
            # Safely get assigned user info
            try:
                if task.assigned_to:
                    user = task.assigned_to
                    # Safely get user name
                    try:
                        if hasattr(user, 'get_full_name') and callable(getattr(user, 'get_full_name')):
                            user_name = request.user.get_full_name()
                        else:
                            user_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
                        
                        if not user_name:
                            user_name = getattr(user, 'username', 'Unknown User')
                    except:
                        user_name = 'Unknown User'
                    
                    response_data['task']['assigned_to'] = {
                        'id': int(user.id),
                        'name': str(user_name),
                    }
                else:
                    response_data['task']['assigned_to'] = {
                        'id': None,
                        'name': None,
                    }
            except Exception as e:
                logger.warning(f"Error getting assigned user info: {e}")
                response_data['task']['assigned_to'] = {
                    'id': None,
                    'name': None,
                }
            
            # Safely get status info
            try:
                if hasattr(task, 'status') and task.status:
                    status_obj = task.status
                    response_data['task']['status'] = {
                        'id': getattr(status_obj, 'id', None),
                        'name': str(getattr(status_obj, 'name', 'Unknown Status')),
                        'color': str(getattr(status_obj, 'color', '#6b7280')),
                    }
                else:
                    response_data['task']['status'] = {
                        'id': None,
                        'name': 'Not Started',
                        'color': '#6b7280',
                    }
            except Exception as e:
                logger.warning(f"Error getting status info: {e}")
                response_data['task']['status'] = {
                    'id': None,
                    'name': 'Not Started',
                    'color': '#6b7280',
                }
            
            # Safely get priority display
            try:
                if hasattr(task, 'get_priority_display') and callable(getattr(task, 'get_priority_display')):
                    priority_display = task.get_priority_display()
                else:
                    priority_choices = {
                        1: 'Critical',
                        2: 'High', 
                        3: 'Medium',
                        4: 'Low'
                    }
                    priority_display = priority_choices.get(task.priority, f"Priority {task.priority}")
                response_data['task']['priority_display'] = str(priority_display)
            except Exception as e:
                logger.warning(f"Error getting priority display: {e}")
                response_data['task']['priority_display'] = f"Priority {task.priority}"
            
            # Safely get tags
            try:
                if hasattr(task, 'tags'):
                    tags = []
                    for tag in task.tags.all():
                        try:
                            tags.append(str(getattr(tag, 'name', 'Unknown Tag')))
                        except:
                            pass
                    response_data['task']['tags'] = tags
                else:
                    response_data['task']['tags'] = []
            except Exception as e:
                logger.warning(f"Error getting tags: {e}")
                response_data['task']['tags'] = []
            
            logger.info(f"Task creation successful: {task.id}")
            return JsonResponse(response_data)
            
    except json.JSONDecodeError:
        logger.error("Invalid JSON data received")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except ValueError as e:
        logger.error(f"Value error creating task: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Invalid data: {str(e)}'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)
    

    


### ========== TIME TRACKING SYSTEM ========== ###

@login_required
def time_tracking_dashboard(request):
    """
    Comprehensive time tracking dashboard with analytics, reporting,
    and team insights. Provides detailed time utilization metrics.
    """
    
    # ========== DATE RANGE PROCESSING ========== #
    
    date_range = request.GET.get('range', 'week')  # week, month, quarter, year
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')
    
    if custom_start and custom_end:
        start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
    else:
        today = timezone.now().date()
        if date_range == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif date_range == 'month':
            start_date = today.replace(day=1)
            next_month = (start_date + timedelta(days=32)).replace(day=1)
            end_date = next_month - timedelta(days=1)
        elif date_range == 'quarter':
            quarter = (today.month - 1) // 3
            start_date = today.replace(month=quarter*3 + 1, day=1)
            end_date = (start_date + timedelta(days=93)).replace(day=1) - timedelta(days=1)
        else:  # year
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
    
    # ========== USER TIME ENTRIES ========== #
    
    user_entries = TimeEntry.objects.select_related(
        'task__project', 'project'
    ).filter(
        user=request.user,
        start_time__date__range=[start_date, end_date],
        is_active=True
    ).order_by('-start_time')
    
    # ========== TIME ANALYTICS ========== #
    
    time_analytics = user_entries.aggregate(
        total_minutes=Sum('duration_minutes'),
        billable_minutes=Sum('duration_minutes', filter=Q(is_billable=True)),
        approved_minutes=Sum('duration_minutes', filter=Q(is_approved=True)),
        entry_count=Count('id')
    )
    
    # Convert to hours and calculate rates
    total_hours = round((time_analytics['total_minutes'] or 0) / 60, 1)
    billable_hours = round((time_analytics['billable_minutes'] or 0) / 60, 1)
    approved_hours = round((time_analytics['approved_minutes'] or 0) / 60, 1)
    
    # Calculate daily average
    days_in_range = (end_date - start_date).days + 1
    daily_average = round(total_hours / days_in_range, 1) if days_in_range > 0 else 0
    
    # ========== PROJECT TIME BREAKDOWN ========== #
    
    project_breakdown = user_entries.values(
        'project__name', 'project__code', 'project__id'
    ).annotate(
        total_minutes=Sum('duration_minutes'),
        entry_count=Count('id'),
        billable_minutes=Sum('duration_minutes', filter=Q(is_billable=True))
    ).order_by('-total_minutes')
    
    # Convert to hours and calculate percentages
    for project in project_breakdown:
        project['total_hours'] = round(project['total_minutes'] / 60, 1)
        project['billable_hours'] = round((project['billable_minutes'] or 0) / 60, 1)
        project['percentage'] = round(
            (project['total_minutes'] / (time_analytics['total_minutes'] or 1)) * 100, 1
        )
    
    # ========== TASK TIME BREAKDOWN ========== #
    
    task_breakdown = user_entries.values(
        'task__title', 'task__id', 'task__project__name'
    ).annotate(
        total_minutes=Sum('duration_minutes'),
        entry_count=Count('id')
    ).order_by('-total_minutes')[:10]  # Top 10 tasks
    
    for task in task_breakdown:
        task['total_hours'] = round(task['total_minutes'] / 60, 1)
    
    # ========== DAILY TIME DISTRIBUTION ========== #
    
    daily_distribution = user_entries.extra(
        select={'day': 'DATE(start_time)'}
    ).values('day').annotate(
        total_minutes=Sum('duration_minutes'),
        entry_count=Count('id')
    ).order_by('day')
    
    for day_data in daily_distribution:
        day_data['total_hours'] = round(day_data['total_minutes'] / 60, 1)
    
    # ========== PRODUCTIVITY INSIGHTS ========== #
    
    # Most productive hours
    hourly_distribution = user_entries.extra(
        select={'hour': 'EXTRACT(hour FROM start_time)'}
    ).values('hour').annotate(
        total_minutes=Sum('duration_minutes')
    ).order_by('-total_minutes')[:3]
    
    # Entry type distribution
    type_distribution = user_entries.values('entry_type').annotate(
        total_minutes=Sum('duration_minutes')
    ).order_by('-total_minutes')

    # Calculate percentage in Python
    for item in type_distribution:
        item['percentage'] = round(
            (item['total_minutes'] / (time_analytics['total_minutes'] or 1)) * 100, 2
        )
    
    # ========== TEAM COMPARISON (if user manages projects) ========== #
    
    team_comparison = []
    managed_projects = Projects.objects.filter(manager=request.user, is_active=True)
    
    if managed_projects.exists():
        team_members = User.objects.filter(
            projects__in=managed_projects
        ).distinct()
        
        for member in team_members:
            member_time = TimeEntry.objects.filter(
                user=member,
                project__in=managed_projects,
                start_time__date__range=[start_date, end_date]
            ).aggregate(
                total_minutes=Sum('duration_minutes')
            )['total_minutes'] or 0
            
            team_comparison.append({
                'user': member,
                'total_hours': round(member_time / 60, 1),
                'daily_average': round((member_time / 60) / days_in_range, 1)
            })
        
        team_comparison.sort(key=lambda x: x['total_hours'], reverse=True)
    
    # ========== RECENT ENTRIES FOR QUICK EDIT ========== #
    
    recent_entries = user_entries[:10]
    
    # ========== GOALS AND TARGETS ========== #
    
    # Weekly/monthly goals (could be stored in user profile)
    weekly_goal = 40  # hours
    monthly_goal = 160  # hours
    
    if date_range == 'week':
        goal_hours = weekly_goal
    elif date_range == 'month':
        goal_hours = monthly_goal
    else:
        goal_hours = None
    
    goal_progress = round((total_hours / goal_hours) * 100, 1) if goal_hours else None
    
    context = {
        'date_range': date_range,
        'start_date': start_date,
        'end_date': end_date,
        'total_hours': total_hours,
        'billable_hours': billable_hours,
        'approved_hours': approved_hours,
        'daily_average': daily_average,
        'entry_count': time_analytics['entry_count'],
        'project_breakdown': project_breakdown,
        'task_breakdown': task_breakdown,
        'daily_distribution': daily_distribution,
        'hourly_distribution': hourly_distribution,
        'type_distribution': type_distribution,
        'team_comparison': team_comparison,
        'recent_entries': recent_entries,
        'goal_hours': goal_hours,
        'goal_progress': goal_progress,
        'entry_types': TimeEntry.ENTRY_TYPES,
    }
    
    return render(request, 'app/time_tracking_dashboard.html', context)


### ========== COLLABORATION AND COMMUNICATION ========== ###

@login_required
@require_POST
@rate_limit('comment_create', max_requests=100, window_seconds=3600)
def add_comment_ajax(request):
    """
    AJAX endpoint for adding comments to projects, tasks, or any content type.
    Supports mentions, threading, and real-time notifications.
    """
    try:
        with transaction.atomic():
            data = json.loads(request.body)
            
            # Validate required fields
            if not data.get('content') or not data.get('content_type') or not data.get('object_id'):
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required fields'
                }, status=400)
            
            # Get content type and object
            try:
                content_type = ContentType.objects.get(
                    app_label='app',
                    model=data['content_type'].lower()
                )
                content_object = content_type.get_object_for_this_type(
                    id=data['object_id']
                )
            except (ContentType.DoesNotExist, content_type.model_class().DoesNotExist):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid content type or object'
                }, status=400)
            
            # Permission check
            can_comment = False
            
            if hasattr(content_object, 'project'):
                # Task or project-related object
                project = getattr(content_object, 'project', content_object)
                can_comment = (
                    project.is_public or
                    project.manager == request.user or
                    request.user in project.team_members.all() or
                    request.user.has_perm('app.comment')
                )
            elif isinstance(content_object, Projects):
                # Direct project comment
                can_comment = (
                    content_object.is_public or
                    content_object.manager == request.user or
                    request.user in content_object.team_members.all() or
                    request.user.has_perm('app.comment')
                )
            
            if not can_comment:
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied'
                }, status=403)
            
            # Create comment
            comment = Comment(
                content=data['content'],
                content_type=content_type,
                object_id=str(content_object.id),
                author=request.user,
                comment_type=data.get('comment_type', 'comment'),
                is_private=data.get('is_private', False)
            )
            
            # Handle parent comment (threading)
            if data.get('parent_id'):
                parent_comment = get_object_or_404(
                    Comment,
                    id=data['parent_id'],
                    content_type=content_type,
                    object_id=str(content_object.id),
                    is_deleted=False
                )
                comment.parent_comment = parent_comment
            
            comment.save()
            
            # Process mentions
            mentioned_users = []
            content_words = comment.content.split()
            
            for word in content_words:
                if word.startswith('@'):
                    username = word[1:].strip('.,!?')
                    try:
                        mentioned_user = User.objects.get(username=username)
                        mentioned_users.append(mentioned_user)
                        comment.mentions.add(mentioned_user)
                    except User.DoesNotExist:
                        pass
            
            # Log activity
            log_activity(
                user=request.user,
                action_type='comment',
                content_object=content_object,
                description=f"Added comment: {comment.content[:50]}...",
                related_project=getattr(content_object, 'project', content_object if isinstance(content_object, Projects) else None)
            )
            
            # Send notifications
            notification_recipients = set()
            
            # Notify mentioned users
            for user in mentioned_users:
                if user != request.user:
                    notification_recipients.add(user)
                    send_notification(
                        recipient=user,
                        notification_type='mention',
                        title=f'You were mentioned in a comment',
                        message=f'{request.user.get_full_name()} mentioned you: {comment.content[:100]}...',
                        content_object=content_object,
                        action_url=getattr(content_object, 'get_absolute_url', lambda: '#')()
                    )
            
            # Notify object owner/assignee
            if hasattr(content_object, 'assigned_to') and content_object.assigned_to:
                if content_object.assigned_to != request.user:
                    notification_recipients.add(content_object.assigned_to)
            elif hasattr(content_object, 'manager') and content_object.manager:
                if content_object.manager != request.user:
                    notification_recipients.add(content_object.manager)
            
            # Send general comment notifications
            for user in notification_recipients:
                if user not in mentioned_users:  # Avoid duplicate notifications
                    send_notification(
                        recipient=user,
                        notification_type='comment_added',
                        title=f'New comment on {content_object}',
                        message=f'{request.user.get_full_name()} added a comment: {comment.content[:100]}...',
                        content_object=content_object,
                        action_url=getattr(content_object, 'get_absolute_url', lambda: '#')()
                    )
            
            # Return comment data
            return JsonResponse({
                'success': True,
                'comment': {
                    'id': str(comment.id),
                    'content': comment.content,
                    'author': {
                        'id': comment.author.id,
                        'name': comment.author.get_full_name(),
                        'username': comment.author.username,
                    },
                    'created_at': comment.created_at.isoformat(),
                    'comment_type': comment.comment_type,
                    'is_private': comment.is_private,
                    'mentions': [user.username for user in comment.mentions.all()],
                    'parent_id': str(comment.parent_comment.id) if comment.parent_comment else None,
                    'reply_count': 0,
                    'like_count': 0,
                }
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating comment: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


### ========== ADVANCED SEARCH AND FILTERING ========== ###

@login_required
def workspace_search(request):
    """
    Global workspace search across projects, tasks, comments, and resources.
    Supports advanced filtering, sorting, and faceted search.
    """
    
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'all')  # all, projects, tasks, comments, resources
    filters = {
        'date_from': request.GET.get('date_from'),
        'date_to': request.GET.get('date_to'),
        'user_id': request.GET.get('user'),
        'project_id': request.GET.get('project'),
        'priority': request.GET.get('priority'),
        'status': request.GET.get('status'),
        'tags': request.GET.get('tags'),
    }
    
    if not query:
        return render(request, 'app/workspace_search.html', {
            'query': query,
            'results': {},
            'facets': {},
        })
    
    results = {}
    facets = {}
    
    # ========== PROJECT SEARCH ========== #
    
    if search_type in ['all', 'projects']:
        project_query = Projects.objects.select_related('manager', 'status').filter(
            Q(is_public=True) | Q(manager=request.user) | Q(team_members=request.user),
            is_active=True
        ).distinct()
        
        # Text search
        project_query = project_query.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(code__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
        
        # Apply filters
        if filters['date_from']:
            project_query = project_query.filter(start_date__gte=filters['date_from'])
        if filters['date_to']:
            project_query = project_query.filter(start_date__lte=filters['date_to'])
        if filters['user_id']:
            project_query = project_query.filter(
                Q(manager_id=filters['user_id']) | Q(team_members__id=filters['user_id'])
            )
        if filters['priority']:
            project_query = project_query.filter(priority=filters['priority'])
        if filters['status']:
            project_query = project_query.filter(status_id=filters['status'])
        
        results['projects'] = project_query.order_by('-updated_at')[:20]
    
    # ========== TASK SEARCH ========== #
    
    if search_type in ['all', 'tasks']:
        task_query = Task.objects.select_related(
            'project', 'assigned_to', 'status'
        ).filter(
            project__in=Projects.objects.filter(
                Q(is_public=True) | Q(manager=request.user) | Q(team_members=request.user)
            ),
            is_active=True
        )
        
        # Text search
        task_query = task_query.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
        
        # Apply filters
        if filters['date_from']:
            task_query = task_query.filter(due_date__gte=filters['date_from'])
        if filters['date_to']:
            task_query = task_query.filter(due_date__lte=filters['date_to'])
        if filters['user_id']:
            task_query = task_query.filter(assigned_to_id=filters['user_id'])
        if filters['project_id']:
            task_query = task_query.filter(project_id=filters['project_id'])
        if filters['priority']:
            task_query = task_query.filter(priority=filters['priority'])
        if filters['status']:
            task_query = task_query.filter(status_id=filters['status'])
        
        results['tasks'] = task_query.order_by('-updated_at')[:20]
    
    # ========== COMMENT SEARCH ========== #
    
    if search_type in ['all']:
        
        # Filter by accessible projects/tasks
        accessible_projects = Projects.objects.filter(
            Q(is_public=True) | Q(manager=request.user) | Q(team_members=request.user)
        ).values_list('id', flat=True)
        
        comment_query = comment_query.filter(
            Q(content_type=ContentType.objects.get_for_model(Projects),
              object_id__in=[str(pk) for pk in accessible_projects]) |
            Q(content_type=ContentType.objects.get_for_model(Task),
              content_object__project__id__in=accessible_projects)
        )
        
        # Apply date filters
        if filters['date_from']:
            comment_query = comment_query.filter(created_at__date__gte=filters['date_from'])
        if filters['date_to']:
            comment_query = comment_query.filter(created_at__date__lte=filters['date_to'])
        if filters['user_id']:
            comment_query = comment_query.filter(author_id=filters['user_id'])
        
       
    
    # ========== RESOURCE SEARCH ========== #
    
    if search_type in ['all', 'resources']:
        resource_query = Resource.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__name__icontains=query),
            is_active=True
        ).distinct()
        
        # Access control
        resource_query = resource_query.filter(
            Q(access_level='public') |
            Q(access_level='internal') |
            Q(allowed_users=request.user)
        ).distinct()
        
        results['resources'] = resource_query.order_by('-view_count', '-updated_at')[:20]
    
    # ========== SEARCH FACETS ========== #
    
    # Calculate facets for filtering
    if results:
        # User facets
        all_users = set()
        for result_type, items in results.items():
            if result_type == 'projects':
                all_users.update(item.manager for item in items if item.manager)
                for project in items:
                    all_users.update(project.team_members.all())
            elif result_type == 'tasks':
                all_users.update(item.assigned_to for item in items if item.assigned_to)
           
        
        facets['users'] = sorted(all_users, key=lambda u: u.get_full_name())
        
        # Project facets
        if 'tasks' in results:
            project_ids = set()
            if 'tasks' in results:
                project_ids.update(task.project.id for task in results['tasks'])
            #
            
            facets['projects'] = Projects.objects.filter(id__in=project_ids)
    
    # ========== SEARCH STATISTICS ========== #
    
    total_results = sum(len(items) for items in results.values())
    
    context = {
        'query': query,
        'search_type': search_type,
        'results': results,
        'facets': facets,
        'total_results': total_results,
        'filters': filters,
        'available_priorities': Task.PRIORITY_LEVELS,
        'available_statuses': TaskStatus.objects.filter(is_active=True),
    }
    
    return render(request, 'app/workspace_search.html', context)


### ========== NOTIFICATION AND ACTIVITY MANAGEMENT ========== ###

@login_required
def notification_center(request):
    """
    Comprehensive notification center with filtering, bulk actions,
    and real-time updates. Provides full notification management.
    """
    
    # ========== QUERY PARAMETERS ========== #
    
    filter_type = request.GET.get('type', 'all')  # all, unread, mentions, tasks, etc.
    page_num = request.GET.get('page', 1)
    
    # ========== BASE QUERYSET ========== #
    
    notifications = Notification.objects.select_related(
        'sender', 'content_type'
    ).filter(
        recipient=request.user,
        is_active=True
    )
    
    # ========== APPLY FILTERS ========== #
    
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_type == 'mentions':
        notifications = notifications.filter(notification_type='mention')
    elif filter_type == 'tasks':
        notifications = notifications.filter(
            notification_type__in=['task_assigned', 'task_due', 'task_completed']
        )
    elif filter_type == 'projects':
        notifications = notifications.filter(
            notification_type__in=['project_updated', 'milestone_reached']
        )
    
    # ========== PAGINATION ========== #
    
    paginator = Paginator(notifications.order_by('-created_at'), 25)
    
    try:
        notifications_page = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        notifications_page = paginator.page(1)
    
    # ========== NOTIFICATION SUMMARY ========== #
    
    summary = {
        'total': Notification.objects.filter(recipient=request.user, is_active=True).count(),
        'unread': Notification.objects.filter(recipient=request.user, is_read=False, is_active=True).count(),
        'mentions': Notification.objects.filter(recipient=request.user, notification_type='mention', is_active=True).count(),
        'tasks': Notification.objects.filter(
            recipient=request.user,
            notification_type__in=['task_assigned', 'task_due', 'task_completed'],
            is_active=True
        ).count(),
    }
    
    context = {
        'notifications': notifications_page,
        'summary': summary,
        'filter_type': filter_type,
        'notification_types': Notification.NOTIFICATION_TYPES,
    }
    
    return render(request, 'app/notification_center.html', context)


@login_required
@require_POST
def mark_notifications_read(request):
    """
    AJAX endpoint for marking notifications as read (individual or bulk).
    """
    try:
        data = json.loads(request.body)
        notification_ids = data.get('notification_ids', [])
        mark_all = data.get('mark_all', False)
        
        if mark_all:
            # Mark all user's notifications as read
            updated_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
                is_active=True
            ).update(
                is_read=True,
                read_at=timezone.now()
            )
        elif notification_ids:
            # Mark specific notifications as read
            updated_count = Notification.objects.filter(
                id__in=notification_ids,
                recipient=request.user,
                is_read=False,
                is_active=True
            ).update(
                is_read=True,
                read_at=timezone.now()
            )
        else:
            return JsonResponse({
                'success': False,
                'error': 'No notifications specified'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'updated_count': updated_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error marking notifications as read: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)



@login_required
def event_list(request):
    """
    Display and filter events with comprehensive filtering options.
    Accessible to all authenticated users with proper scoping.
    """
    # Base queryset - only show active events
    events = Event.objects.select_related(
        'created_by', 'related_project'
    ).prefetch_related(
        'participants', 'tags'
    ).filter(is_active=True)
    
    # Apply filters
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    mandatory_filter = request.GET.get('mandatory', '')
    event_type_filter = request.GET.get('event_type', '')
    
    if search_query:
        events = events.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Date-based filters
    now = timezone.now()
    if status_filter == 'upcoming':
        events = events.filter(start_time__gte=now)
    elif status_filter == 'past':
        events = events.filter(end_time__lt=now)
    elif status_filter == 'today':
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        events = events.filter(
            start_time__gte=today_start,
            start_time__lt=today_end
        )
    elif status_filter == 'this_week':
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        events = events.filter(
            start_time__gte=week_start,
            start_time__lt=week_end
        )
    
    # Mandatory filter
    if mandatory_filter == 'mandatory':
        events = events.filter(is_mandatory=True)
    elif mandatory_filter == 'optional':
        events = events.filter(is_mandatory=False)
    
    # Event type filter
    if event_type_filter:
        events = events.filter(event_type=event_type_filter)
    
    # Order by start time (upcoming first)
    events = events.order_by('start_time')
    
    # Pagination
    paginator = Paginator(events, 20)
    page = request.GET.get('page', 1)
    
    try:
        events_page = paginator.page(page)
    except PageNotAnInteger:
        events_page = paginator.page(1)
    except EmptyPage:
        events_page = paginator.page(paginator.num_pages)
    
    context = {
        'events': events_page,
        'event_types': Event.EVENT_TYPES,
        'current_filters': {
            'search': search_query,
            'status': status_filter,
            'mandatory': mandatory_filter,
            'event_type': event_type_filter,
        }
    }
    
    return render(request, 'app/event_list.html', context)


@login_required
@permission_required('app.manage_events', raise_exception=True)
def create_event(request):
    """
    Create a new event with comprehensive validation and error handling.
    Handles both one-time and recurring events with participant notifications.
    """
    if request.method == 'POST':
        form = EventForm(request.POST, user=request.user)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create event instance
                    event = form.save(commit=False)
                    event.created_by = request.user
                    
                    event.save()
                    
                    # Save many-to-many relationships
                    form.save_m2m()
                    
                    # Log activity
                    logger.info(
                        f"Event created: {event.title} (ID: {event.id}) by {request.user.username}"
                    )
                    
                    # Send notifications to participants if requested
                    if form.cleaned_data.get('send_notifications', False):
                        try:
                            send_event_notifications(event, request.user)
                        except Exception as e:
                            logger.error(f"Failed to send event notifications: {e}")
                            # Don't fail the entire operation if notifications fail
                            messages.warning(
                                request,
                                'Event created successfully, but some notifications failed to send.'
                            )
                    
                    messages.success(
                        request,
                        f'Event "{event.title}" created successfully!'
                    )
                    return redirect('common:event_detail', pk=event.id)
                    
            except Exception as e:
                logger.error(f"Error creating event: {e}", exc_info=True)
                messages.error(
                    request,
                    'An error occurred while creating the event. Please try again.'
                )
        else:
            # Form validation failed
            messages.error(
                request,
                'Please correct the errors below.'
            )
            logger.warning(
                f"Event creation form validation failed for user {request.user.username}: {form.errors}"
            )
    else:
        # Initialize form with user context
        form = EventForm(user=request.user)
        
        # Set default start time to next hour
        next_hour = (timezone.now() + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )
        form.initial['start_time'] = next_hour
        form.initial['end_time'] = next_hour + timedelta(hours=1)
    
    context = {
        'form': form,
        'page_title': 'Create Event',
        'submit_text': 'Create Event',
    }
    
    return render(request, 'app/event_form.html', context)


@login_required
def event_detail(request, pk):
    """
    Display detailed event information with participation tracking.
    Shows different information based on user's relationship to the event.
    """
    event = get_object_or_404(
        Event.objects.select_related(
            'created_by', 'related_project'
        ).prefetch_related(
            'participants', 'tags', 'attachments'
        ),
        pk=pk,
        is_active=True
    )
    
    # Check if user is a participant
    is_participant = request.user in event.participants.all()
    
    # Get user's RSVP status if participant
    rsvp_status = None
    if is_participant:
        try:
            participation = EventParticipation.objects.get(
                event=event,
                user=request.user
            )
            rsvp_status = participation.rsvp_status
        except EventParticipation.DoesNotExist:
            pass
    
    # Calculate event statistics
    participant_count = event.participants.count()
    accepted_count = EventParticipation.objects.filter(
        event=event,
        rsvp_status='accepted'
    ).count()
    
    context = {
        'event': event,
        'is_participant': is_participant,
        'rsvp_status': rsvp_status,
        'participant_count': participant_count,
        'accepted_count': accepted_count,
        'can_edit': (
            request.user == event.created_by or
            request.user.has_perm('app.manage_events')
        ),
    }
    
    return render(request, 'app/event_detail.html', context)


@login_required
@permission_required('app.manage_events', raise_exception=True)
def edit_event(request, pk):
    """
    Edit existing event with validation and change tracking.
    Notifies participants of significant changes.
    """
    event = get_object_or_404(Event, pk=pk, is_active=True)
    
    # Check permissions
    if not (event.created_by == request.user or request.user.has_perm('app.manage_events')):
        messages.error(request, 'You do not have permission to edit this event.')
        return redirect('common:event_detail', pk=event.id)
    
    # Track original values for change detection
    original_start = event.start_time
    original_location = event.location
    
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event, user=request.user)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_event = form.save()
                    
                    # Detect significant changes
                    changes = []
                    if updated_event.start_time != original_start:
                        changes.append('start time')
                    if updated_event.location != original_location:
                        changes.append('location')
                    
                    # Notify participants of changes
                    if changes and form.cleaned_data.get('send_notifications', False):
                        try:
                            notify_event_changes(updated_event, changes, request.user)
                        except Exception as e:
                            logger.error(f"Failed to send change notifications: {e}")
                    
                    logger.info(
                        f"Event updated: {updated_event.title} (ID: {updated_event.id}) "
                        f"by {request.user.username}"
                    )
                    
                    messages.success(request, 'Event updated successfully!')
                    return redirect('common:event_detail', pk=updated_event.id)
                    
            except Exception as e:
                logger.error(f"Error updating event: {e}", exc_info=True)
                messages.error(
                    request,
                    'An error occurred while updating the event. Please try again.'
                )
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = EventForm(instance=event, user=request.user)
    
    context = {
        'form': form,
        'event': event,
        'page_title': 'Edit Event',
        'submit_text': 'Update Event',
    }
    
    return render(request, 'app/event_form.html', context)


@login_required
@permission_required('app.manage_events', raise_exception=True)
def delete_event(request, pk):
    """
    Soft delete event with participant notification.
    Actually performs soft delete (sets is_active=False) rather than hard delete.
    """
    event = get_object_or_404(Event, pk=pk, is_active=True)
    
    # Check permissions
    if not (event.created_by == request.user or request.user.has_perm('app.manage_events')):
        messages.error(request, 'You do not have permission to delete this event.')
        return redirect('common:event_detail', pk=event.id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Soft delete
                event.is_active = False
                event.save(update_fields=['is_active', 'updated_at'])
                
                # Notify participants
                try:
                    notify_event_cancellation(event, request.user)
                except Exception as e:
                    logger.error(f"Failed to send cancellation notifications: {e}")
                
                logger.info(
                    f"Event deleted: {event.title} (ID: {event.id}) by {request.user.username}"
                )
                
                messages.success(
                    request,
                    f'Event "{event.title}" has been deleted and participants have been notified.'
                )
                return redirect('common:event_list')
                
        except Exception as e:
            logger.error(f"Error deleting event: {e}", exc_info=True)
            messages.error(
                request,
                'An error occurred while deleting the event. Please try again.'
            )
            return redirect('common:event_detail', pk=event.id)
    
    context = {
        'object': event,
        'type': 'Event',
        'cancel_url': 'common:event_detail',
        'cancel_kwargs': {'pk': event.id},
    }
    
    return render(request, 'app/confirm_delete.html', context)


# Helper functions for notifications

def send_event_notifications(event, creator):
    """Send notifications to all event participants."""
    from .notification_utils import create_notification
    
    # Format name from user fields
    creator_name = f"{creator.first_name} {creator.last_name}".strip() or creator.username
    
    for participant in event.participants.exclude(id=creator.id):
        create_notification(
            recipient=participant,
            notification_type='event_reminder',
            title=f'New Event: {event.title}',
            message=f'{creator_name} has invited you to "{event.title}" on {event.start_time.strftime("%B %d, %Y at %I:%M %p")}',
            content_object=event,
            sender=creator,
            action_url=event.get_absolute_url()
        )


def notify_event_changes(event, changes, updater):
    """Notify participants of significant event changes."""
    from .utils import send_notification
    
    changes_text = ', '.join(changes)
    
    for participant in event.participants.exclude(id=updater.id):
        send_notification(
            recipient=participant,
            notification_type='event_updated',
            title=f'Event Updated: {event.title}',
            message=f'{updater.get_full_name()} has updated the {changes_text} for "{event.title}"',
            content_object=event,
            action_url=event.get_absolute_url()
        )


def notify_event_cancellation(event, canceller):
    """Notify participants of event cancellation."""
    from .utils import send_notification
    
    for participant in event.participants.exclude(id=canceller.id):
        send_notification(
            recipient=participant,
            notification_type='event_cancelled',
            title=f'Event Cancelled: {event.title}',
            message=f'{canceller.get_full_name()} has cancelled "{event.title}" scheduled for {event.start_time.strftime("%B %d, %Y at %I:%M %p")}',
            content_object=event,
            action_url='/events/'
        )
### ========== ANNOUNCEMENTS ========== ###

@login_required
def announcement_list(request):
    announcements = Announcement.objects.all()
    return render(request, 'app/announcement_list.html', {'announcements': announcements})

@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def create_announcement(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.created_by = request.user
            ann.save()
            messages.success(request, 'Announcement posted successfully.')
            return redirect('common:announcement_list')
    else:
        form = AnnouncementForm()
    return render(request, 'app/announcement_form.html', {'form': form})



@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def create_announcement(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.created_by = request.user
            ann.save()
            messages.success(request, 'Announcement posted successfully.')
            return redirect('common:announcement_list')
    else:
        form = AnnouncementForm()
    return render(request, 'app/announcement_form.html', {'form': form})


@login_required
def announcement_detail(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    return render(request, 'app/announcement_detail.html', {'announcement': announcement})


@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def edit_announcement(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated successfully.')
            return redirect('common:announcement_detail', pk=announcement.pk)
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, 'app/announcement_form.html', {'form': form})


@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def delete_announcement(request, pk):
    announcement = get_object_or_404(Announcement, id=pk)
    if request.method == 'POST':
        announcement.delete()
        messages.success(request, 'Announcement deleted successfully.')
        return redirect('common:announcement_list')
    return render(request, 'app/confirm_delete.html', {
        'object': announcement,
        'type': 'Announcement',
        'cancel_url': 'common:announcement_detail',
        'cancel_id': announcement.id
    })




### ========== PROJECTS ========== ###
@login_required
@permission_required_or_owner('app.manage_projects', Projects, pk_field='project_id')
def project_kanban(request, project_id):
    """
    Project-specific kanban board - subset of workspace kanban for single project.
    """
    project = get_object_or_404(Projects, id=project_id, is_active=True)
    
    # Get all active task statuses for kanban columns
    kanban_statuses = TaskStatus.objects.filter(is_active=True).order_by('order')
    
    # Get tasks for this project only
    tasks_query = Task.objects.select_related(
        'assigned_to', 'status', 'created_by'
    ).prefetch_related(
        'tags', 'dependencies'
    ).filter(
        project=project,
        is_active=True
    )
    
    # Organize tasks by status
    kanban_columns = []
    for status in kanban_statuses:
        status_tasks = tasks_query.filter(status=status).order_by('-priority', 'due_date')
        kanban_columns.append({
            'status': status,
            'tasks': status_tasks,
            'count': status_tasks.count()
        })
    
    context = {
        'project': project,
        'kanban_columns': kanban_columns,
        'can_edit': (
            project.manager == request.user or
            request.user in project.team_members.all() or
            request.user.has_perm('app.manage_tasks')
        ),
    }
    
    return render(request, 'app/project_kanban.html', context)

@login_required
def task_detail_ajax(request, pk):
    task = get_object_or_404(Task, pk=pk)
    data = {
        'title': task.title,
        'description': task.description,
        'due_date': task.due_date.strftime('%Y-%m-%d'),
        'status': task.get_status_display(),
        'assigned_to': (
            str(task.assigned_to.get_full_name()) 
            if task.assigned_to and hasattr(task.assigned_to, 'get_full_name') and callable(getattr(task.assigned_to, 'get_full_name'))
            else (
                f"{getattr(task.assigned_to, 'first_name', '')} {getattr(task.assigned_to, 'last_name', '')}".strip()
                if task.assigned_to and hasattr(task.assigned_to, 'first_name')
                else str(task.assigned_to) if task.assigned_to else None
            )
        ),
        'attachment_url': task.attachment.url if task.attachment else None,
        'tags': [t.name for t in task.tags.all()],
        'priority': task.get_priority_display(),
    }
    return JsonResponse(data)

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            form.save()
            #notify_user(request.user, f'Project {proj.name} created.')
            messages.success(request, 'Project created successfully.')
            return redirect('common:project_list')
    else:
        form = ProjectForm()
    return render(request, 'app/project_form.html', {'form': form})


@login_required
@permission_required('app.manage_projects', raise_exception=True)
def edit_project(request, project_id):
    proj=get_object_or_404(Projects,id=project_id)
    form=ProjectForm(request.POST or None, request.FILES or None, instance=proj)
    if form.is_valid():
        proj=form.save()
        #notify_user(request.user, f'Project {proj.name} updated.')
        messages.success(request,'Project updated.')
        return redirect('common:project_kanban', id=project_id)
    return render(request,'app/project_form.html',{'form':form,'project':proj})

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def delete_project(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    if request.method == 'POST':
        project.delete()
        #notify_user(request.user, f'Project {proj.name} deleted.')
        messages.success(request, 'Project deleted successfully.')
        return redirect('common:project_list')
    return render(request, 'app/confirm_delete.html', {
        'object': project, 'type': 'Project',
        'cancel_url': 'project_detail', 'cancel_id': project.id
    })


### ========== TASKS ========== ###

@login_required
def task_list(request):
    tasks = Task.objects.select_related('project_task').all()
    return render(request, 'app/task_list.html', {'tasks': tasks})


@require_http_methods(["POST"])
@login_required
def create_task(request):
    form = TaskForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            task = form.save(commit=False)
            task.created_by = request.user
            
            # Fix: Don't set status to string, let the form/model handle it
            if not task.status:
                initial_status = TaskStatus.objects.filter(is_initial=True, is_active=True).first()
                if initial_status:
                    task.status = initial_status
            
            task.save()
            form.save_m2m()  # Save tags
            
            return JsonResponse({
                'status': 'ok',
                'task': {
                    'id': str(task.id),  # Convert UUID to string
                    'title': task.title,
                    'status': task.status.name if task.status else task.legacy_status,
                    'due_date': task.due_date.strftime('%Y-%m-%d')
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'error': form.errors}, status=400)


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    return render(request, 'app/task_detail.html', {'task': task})

@require_http_methods(["POST"])
@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    form = TaskForm(request.POST, request.FILES, instance=task)
    if form.is_valid():
        try:
            task = form.save()
            return JsonResponse({
                'status': 'ok',
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'due_date': task.due_date.strftime('%Y-%m-%d')
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'error': form.errors}, status=400)

# Update delete_task view
@require_http_methods(["POST"])
@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    try:
        task.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=400)





@login_required
@require_POST
def move_task(request, pk):
    try:
        task = get_object_or_404(Task, pk=pk)
        data = json.loads(request.body)
        new_status_id = data.get('status_id')
        
        # Use TaskStatus model instead of legacy choices
        new_status = get_object_or_404(TaskStatus, id=new_status_id, is_active=True)
        
        task.status = new_status
        task.save()
        
        return JsonResponse({
            'status': 'ok',
            'task': {
                'id': str(task.id),
                'status': new_status.name,
                'status_color': new_status.color
            }
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=400)
    


### ========== RESOURCES ========== ###

@login_required
def resource_list(request):
    resources = Resource.objects.all()
    return render(request, 'app/resource_list.html', {'resources': resources})

@login_required
def create_resource(request):
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            res = form.save(commit=False)
            res.created_by = request.user
            res.save()
            messages.success(request, 'Resource created successfully.')
            return redirect('common:resource_list')
    else:
        form = ResourceForm()
    return render(request, 'app/resource_form.html', {'form': form})

@login_required
def resource_detail(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    return render(request, 'app/resource_detail.html', {'resource': resource})

@login_required
def edit_resource(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resource updated successfully.')
            return redirect('common:resource_detail', resource_id=resource.id)
    else:
        form = ResourceForm(instance=resource)
    return render(request, 'app/resource_form.html', {'form': form})

@login_required
def delete_resource(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if request.method == 'POST':
        resource.delete()
        messages.success(request, 'Resource deleted successfully.')
        return redirect('common:resource_list')
    return render(request, 'app/confirm_delete.html', {
        'object': resource, 'type': 'Resource',
        'cancel_url': 'resource_detail', 'cancel_id': resource.id
    })



### ========== NOTIFICATIONS ========== ###
@login_required
def notification_list(request):
    """Display all notifications for the user."""
    notifications = Notification.objects.filter(
        recipient=request.user,
        is_active=True
    ).select_related('sender', 'content_type').order_by('-created_at')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page', 1)
    
    try:
        notifications_page = paginator.page(page)
    except:
        notifications_page = paginator.page(1)
    
    context = {
        'notifications': notifications_page,
        'page_title': 'All Notifications',
    }
    
    return render(request, 'app/notifications/list.html', context)


@login_required
@require_http_methods(["POST"])
def notification_mark_read(request, pk):
    """Mark a notification as read via AJAX."""
    success = mark_notification_read(pk, request.user)
    
    if success:
        return JsonResponse({
            'success': True,
            'unread_count': get_unread_count(request.user)
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Notification not found'
    }, status=404)


@login_required
@require_http_methods(["POST"])
def notification_mark_all_read(request):
    """Mark all notifications as read via AJAX."""
    count = mark_all_read(request.user)
    
    return JsonResponse({
        'success': True,
        'marked_count': count,
        'unread_count': 0
    })


@login_required
@require_http_methods(["POST"])
def notification_delete(request, pk):
    """Delete a notification via AJAX."""
    success = delete_notification(pk, request.user)
    
    if success:
        return JsonResponse({
            'success': True,
            'unread_count': get_unread_count(request.user)
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Notification not found'
    }, status=404)


@login_required
def notification_fetch(request):
    """Fetch recent notifications via AJAX for real-time updates."""
    notifications = get_recent_notifications(request.user, limit=10)
    
    notifications_data = []
    for notification in notifications:
        sender_name = None
        notifications_data.append({
            'id': str(notification.id),
            'title': notification.title,
            'message': notification.message,
            'type': notification.notification_type,
            'is_read': notification.is_read,
            'action_url': notification.action_url,
            'created_at': notification.created_at.isoformat(),
            'sender_name': sender_name,
        })
    
    return JsonResponse({
        'success': True,
        'notifications': notifications_data,
        'unread_count': get_unread_count(request.user)
    })





import logging
import traceback
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from functools import wraps

from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.views.decorators.cache import never_cache
from django.utils import timezone

# Import error tracking services (install via pip)
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# Configure structured logging
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

class ErrorHandlerConfig:
    """
    Centralized configuration for error handling behavior.
    
    This class manages all configurable aspects of error handling,
    making it easy to adjust behavior across environments.
    """
    
    # Error page rate limiting (prevent abuse/DDoS)
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = 10  # Max requests per window
    RATE_LIMIT_WINDOW = 60    # Window in seconds
    
    # Error tracking and monitoring
    ENABLE_SENTRY = getattr(settings, 'SENTRY_ENABLED', SENTRY_AVAILABLE)
    ENABLE_DATABASE_LOGGING = getattr(settings, 'ERROR_DB_LOGGING', True)
    ENABLE_EMAIL_ALERTS = getattr(settings, 'ERROR_EMAIL_ALERTS', not settings.DEBUG)
    
    # Response behavior
    SHOW_DEBUG_INFO = settings.DEBUG
    SHOW_STACK_TRACES = settings.DEBUG
    INCLUDE_REQUEST_HEADERS = settings.DEBUG
    
    # Security settings
    SANITIZE_SENSITIVE_DATA = True
    SENSITIVE_KEYS = [
        'password', 'secret', 'api_key', 'token', 'authorization',
        'cookie', 'session', 'csrf', 'private_key'
    ]
    
    # Performance monitoring
    LOG_SLOW_ERRORS = True
    SLOW_ERROR_THRESHOLD = 1.0  # Seconds


# ============================================================================
# CUSTOM EXCEPTION CLASSES
# ============================================================================

class BaseApplicationError(Exception):
    """
    Base exception class for all application-specific errors.
    
    Provides structured error information and consistent handling
    across the application.
    """
    
    def __init__(
        self, 
        message: str,
        error_code: str = None,
        status_code: int = 500,
        user_message: str = None,
        context: Dict[str, Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.status_code = status_code
        self.user_message = user_message or message
        self.context = context or {}
        self.timestamp = timezone.now()


class ResourceNotFoundError(BaseApplicationError):
    """Raised when a requested resource doesn't exist."""
    
    def __init__(self, resource_type: str, identifier: str, **kwargs):
        message = f"{resource_type} with identifier '{identifier}' not found"
        super().__init__(
            message=message,
            error_code='RESOURCE_NOT_FOUND',
            status_code=404,
            user_message=f"The {resource_type.lower()} you're looking for doesn't exist.",
            **kwargs
        )


class InsufficientPermissionsError(BaseApplicationError):
    """Raised when user lacks required permissions."""
    
    def __init__(self, required_permission: str, **kwargs):
        message = f"Permission denied: requires '{required_permission}'"
        super().__init__(
            message=message,
            error_code='INSUFFICIENT_PERMISSIONS',
            status_code=403,
            user_message="You don't have permission to perform this action.",
            **kwargs
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_error_id(request: HttpRequest, error: Exception) -> str:
    """
    Generate a unique, reproducible error ID for tracking.
    
    This ID allows users to reference specific errors when contacting support,
    and helps correlate error instances in logs and monitoring systems.
    
    Args:
        request: The HTTP request that triggered the error
        error: The exception that was raised
        
    Returns:
        A unique 16-character hexadecimal error ID
    """
    timestamp = datetime.now().isoformat()
    path = request.path
    error_type = type(error).__name__
    
    # Create deterministic hash from error context
    hash_input = f"{timestamp}:{path}:{error_type}:{str(error)}"
    error_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    
    return error_hash[:16].upper()


def sanitize_data(data: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """
    Recursively sanitize sensitive data from dictionaries and objects.
    
    Prevents accidental exposure of passwords, tokens, and other sensitive
    information in error logs and responses. Uses a whitelist approach for
    known sensitive key patterns.
    
    Args:
        data: Data structure to sanitize (dict, list, or primitive)
        depth: Current recursion depth (internal use)
        max_depth: Maximum recursion depth to prevent infinite loops
        
    Returns:
        Sanitized copy of the input data
    """
    if depth > max_depth:
        return "[MAX_DEPTH_EXCEEDED]"
    
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Check if key contains sensitive patterns
            key_lower = str(key).lower()
            is_sensitive = any(
                sensitive in key_lower 
                for sensitive in ErrorHandlerConfig.SENSITIVE_KEYS
            )
            
            if is_sensitive:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_data(value, depth + 1, max_depth)
        return sanitized
    
    elif isinstance(data, (list, tuple)):
        return [sanitize_data(item, depth + 1, max_depth) for item in data]
    
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    
    else:
        # For unknown types, convert to string representation
        return str(data)


def capture_request_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Extract comprehensive context from the request for debugging.
    
    Captures all relevant request information while respecting security
    and privacy constraints. This data is invaluable for reproducing
    and diagnosing errors.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Dictionary containing sanitized request context
    """
    context = {
        'method': request.method,
        'path': request.path,
        'full_path': request.get_full_path(),
        'scheme': request.scheme,
        'user': {
            'id': getattr(request.user, 'id', None),
            'username': getattr(request.user, 'username', 'anonymous'),
            'is_authenticated': request.user.is_authenticated,
            'is_staff': getattr(request.user, 'is_staff', False),
        },
        'session': {
            'session_key': request.session.session_key if hasattr(request, 'session') else None,
            'exists': hasattr(request, 'session'),
        },
        'client': {
            'ip': get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
            'referrer': request.META.get('HTTP_REFERER', None),
        },
        'query_params': dict(request.GET.items()),
        'timestamp': timezone.now().isoformat(),
    }
    
    # Include headers only if configured (DEBUG mode)
    if ErrorHandlerConfig.INCLUDE_REQUEST_HEADERS:
        context['headers'] = {
            k: v for k, v in request.META.items()
            if k.startswith('HTTP_')
        }
    
    # Sanitize sensitive data
    if ErrorHandlerConfig.SANITIZE_SENSITIVE_DATA:
        context = sanitize_data(context)
    
    return context


def get_client_ip(request: HttpRequest) -> str:
    """
    Extract the real client IP address, accounting for proxies.
    
    Checks X-Forwarded-For and X-Real-IP headers to handle reverse
    proxies and CDNs correctly.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Client IP address as a string
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain (actual client)
        return x_forwarded_for.split(',')[0].strip()
    
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip.strip()
    
    return request.META.get('REMOTE_ADDR', 'unknown')


def check_rate_limit(request: HttpRequest, error_code: str) -> Tuple[bool, int]:
    """
    Implement rate limiting for error pages to prevent abuse.
    
    Uses Django's cache framework to track error page requests per IP.
    This prevents attackers from overwhelming the system by triggering
    errors repeatedly.
    
    Args:
        request: The HTTP request object
        error_code: The error code being handled
        
    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    if not ErrorHandlerConfig.RATE_LIMIT_ENABLED:
        return True, ErrorHandlerConfig.RATE_LIMIT_REQUESTS
    
    client_ip = get_client_ip(request)
    cache_key = f"error_rate_limit:{error_code}:{client_ip}"
    
    # Get current request count
    request_count = cache.get(cache_key, 0)
    
    if request_count >= ErrorHandlerConfig.RATE_LIMIT_REQUESTS:
        return False, 0
    
    # Increment counter
    cache.set(
        cache_key,
        request_count + 1,
        ErrorHandlerConfig.RATE_LIMIT_WINDOW
    )
    
    remaining = ErrorHandlerConfig.RATE_LIMIT_REQUESTS - request_count - 1
    return True, remaining


def log_error_to_monitoring(
    error: Exception,
    request: HttpRequest,
    error_id: str,
    context: Dict[str, Any]
) -> None:
    """
    Send error information to external monitoring services.
    
    Integrates with services like Sentry, Rollbar, or custom logging
    infrastructure. Includes full context for debugging while respecting
    security constraints.
    
    Args:
        error: The exception that occurred
        request: The HTTP request object
        error_id: Unique identifier for this error instance
        context: Additional context information
    """
    # Log to Sentry if available and enabled
    if ErrorHandlerConfig.ENABLE_SENTRY and SENTRY_AVAILABLE:
        with sentry_sdk.push_scope() as scope:
            # Add custom context
            scope.set_context("error_details", {
                "error_id": error_id,
                "error_type": type(error).__name__,
            })
            scope.set_context("request_context", context)
            
            # Set user context
            if request.user.is_authenticated:
                scope.set_user({
                    "id": request.user.id,
                    "username": request.user.username,
                })
            
            # Capture the exception
            sentry_sdk.capture_exception(error)
    
    # Log to structured logger
    logger.error(
        f"Error {error_id}: {type(error).__name__}",
        extra={
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'request_context': context,
            'stack_trace': traceback.format_exc() if ErrorHandlerConfig.SHOW_STACK_TRACES else None,
        },
        exc_info=True
    )


def is_api_request(request: HttpRequest) -> bool:
    """
    Determine if the request expects a JSON response.
    
    Checks Accept headers and URL patterns to decide whether to return
    JSON (for API clients) or HTML (for browsers).
    
    Args:
        request: The HTTP request object
        
    Returns:
        True if the request expects JSON, False otherwise
    """
    # Check Accept header
    accept = request.META.get('HTTP_ACCEPT', '')
    if 'application/json' in accept:
        return True
    
    # Check if path starts with /api/
    if request.path.startswith('/api/'):
        return True
    
    # Check for explicit JSON format parameter
    if request.GET.get('format') == 'json':
        return True
    
    return False


# ============================================================================
# DECORATOR FOR ERROR HANDLING
# ============================================================================

def enhanced_error_handler(error_code: str):
    """
    Decorator that adds advanced error handling to view functions.
    
    This decorator wraps error handlers with additional functionality like
    rate limiting, logging, monitoring, and format detection.
    
    Usage:
        @enhanced_error_handler('404')
        def error_404(request, exception):
            # Your error handling logic
            pass
    
    Args:
        error_code: The HTTP error code being handled
        
    Returns:
        Decorated function with enhanced error handling
    """
    def decorator(func):
        @wraps(func)
        @never_cache  # Prevent caching of error pages
        def wrapper(request, *args, **kwargs):
            start_time = timezone.now()
            
            # Check rate limit
            is_allowed, remaining = check_rate_limit(request, error_code)
            if not is_allowed:
                logger.warning(
                    f"Rate limit exceeded for error {error_code} from {get_client_ip(request)}"
                )
                return render(
                    request,
                    'app/rate_limit.html',
                    {'error_code': '429'},
                    status=429
                )
            
            # Execute the original error handler
            response = func(request, *args, **kwargs)
            
            # Calculate execution time
            execution_time = (timezone.now() - start_time).total_seconds()
            
            # Log slow error handlers
            if (ErrorHandlerConfig.LOG_SLOW_ERRORS and 
                execution_time > ErrorHandlerConfig.SLOW_ERROR_THRESHOLD):
                logger.warning(
                    f"Slow error handler for {error_code}: {execution_time:.2f}s"
                )
            
            return response
        
        return wrapper
    return decorator


# ============================================================================
# ERROR RESPONSE BUILDERS
# ============================================================================

def build_error_context(
    request: HttpRequest,
    error: Exception,
    error_code: str,
    error_message: str,
    suggestions: list = None
) -> Dict[str, Any]:
    """
    Build comprehensive context dictionary for error templates.
    
    Creates a rich context object that includes all necessary information
    for rendering error pages, including technical details, user guidance,
    and debugging information.
    
    Args:
        request: The HTTP request object
        error: The exception that occurred
        error_code: HTTP status code
        error_message: User-friendly error message
        suggestions: List of suggested actions/links
        
    Returns:
        Dictionary of template context variables
    """
    # Generate unique error ID
    error_id = generate_error_id(request, error)
    
    # Capture request context
    request_context = capture_request_context(request)
    
    # Log to monitoring services
    log_error_to_monitoring(error, request, error_id, request_context)
    
    # Build base context
    context = {
        'error_code': error_code,
        'error_message': error_message,
        'request_id': error_id,
        'suggestions': suggestions or [],
        'debug': settings.DEBUG,
        'version': getattr(settings, 'VERSION', 'dev'),
    }
    
    # Add debug information if enabled
    if ErrorHandlerConfig.SHOW_DEBUG_INFO:
        context['error_debug'] = {
            'exception_type': type(error).__name__,
            'exception_message': str(error),
            'request_context': request_context,
        }
        
        if ErrorHandlerConfig.SHOW_STACK_TRACES:
            context['error_debug']['stack_trace'] = traceback.format_exc()
    
    # Add custom exception context if available
    if isinstance(error, BaseApplicationError):
        context['error_context'] = error.context
    
    return context


def build_json_error_response(
    request: HttpRequest,
    error: Exception,
    error_code: str,
    error_message: str,
    status_code: int
) -> JsonResponse:
    """
    Build standardized JSON error response for API requests.
    
    Returns errors in a consistent format that API clients can parse
    and handle programmatically.
    
    Args:
        request: The HTTP request object
        error: The exception that occurred
        error_code: Error code/type
        error_message: Human-readable error message
        status_code: HTTP status code
        
    Returns:
        JsonResponse with error details
    """
    error_id = generate_error_id(request, error)
    request_context = capture_request_context(request)
    
    # Log to monitoring
    log_error_to_monitoring(error, request, error_id, request_context)
    
    response_data = {
        'error': {
            'code': error_code,
            'message': error_message,
            'request_id': error_id,
            'timestamp': timezone.now().isoformat(),
        },
        'status': status_code,
    }
    
    # Add debug info if enabled
    if ErrorHandlerConfig.SHOW_DEBUG_INFO:
        response_data['debug'] = {
            'exception_type': type(error).__name__,
            'exception_message': str(error),
            'path': request.path,
        }
        
        if ErrorHandlerConfig.SHOW_STACK_TRACES:
            response_data['debug']['stack_trace'] = traceback.format_tb(
                error.__traceback__
            )
    
    return JsonResponse(response_data, status=status_code)


# ============================================================================
# ADVANCED ERROR HANDLERS
# ============================================================================

@enhanced_error_handler('404')
def error_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 404 Not Found handler with intelligent suggestions.
    
    Provides context-aware navigation suggestions based on the request path
    and user permissions. Logs 404s for analytics and broken link detection.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 404
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'The page you are looking for could not be found.'
    
    # Build intelligent suggestions based on context
    suggestions = []
    
    # Always offer dashboard for authenticated users
    if request.user.is_authenticated:
        suggestions.append(('Dashboard', '/app/dashboard/'))
    
    # Suggest similar resources based on path
    path_parts = request.path.strip('/').split('/')
    if 'project' in path_parts:
        suggestions.extend([
            ('All Projects', '/app/projects/'),
            ('My Projects', '/app/projects/?filter=my'),
        ])
    elif 'task' in path_parts:
        suggestions.extend([
            ('All Tasks', '/app/tasks/'),
            ('Kanban Board', '/app/kanban/'),
        ])
    
    # Add search option
    suggestions.append(('Search', f'/app/search/?q={path_parts[-1] if path_parts else ""}'))
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '404', error_message, 404
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '404', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=404)


@enhanced_error_handler('500')
def error_500(request: HttpRequest) -> HttpResponse:
    """
    Advanced 500 Internal Server Error handler with incident tracking.
    
    Captures full diagnostic information, creates incident reports,
    and notifies the development team. Provides users with a reference
    ID for support inquiries.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'An internal server error occurred. Our team has been notified.'
    
    # Create a generic exception for 500 errors without an exception object
    exception = Exception("Internal Server Error")
    
    # Suggestions for recovery
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
        ('Refresh Page', request.path),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '500', error_message, 500
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '500', error_message, suggestions
    )
    
    # Additional incident tracking
    error_id = context['request_id']
    logger.critical(
        f"500 Internal Server Error - Incident ID: {error_id}",
        extra={
            'incident_id': error_id,
            'requires_investigation': True,
            'severity': 'CRITICAL',
        }
    )
    
    return render(request, 'app/error.html', context, status=500)


@enhanced_error_handler('403')
def error_403(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 403 Forbidden handler with permission guidance.
    
    Provides detailed information about required permissions and suggests
    ways to gain access. Logs access denial attempts for security monitoring.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 403
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'You do not have permission to access this resource.'
    
    # Build context-aware suggestions
    suggestions = []
    
    if request.user.is_authenticated:
        suggestions.extend([
            ('Dashboard', '/app/dashboard/'),
            ('My Projects', '/app/projects/?filter=my'),
        ])
        
        # Suggest contacting admin if user has limited permissions
        if not request.user.is_staff:
            suggestions.append(('Request Access', '/support/access-request/'))
    else:
        # User is not authenticated - suggest login
        suggestions.extend([
            ('Login', f'/accounts/login/?next={request.path}'),
            ('Sign Up', '/accounts/signup/'),
        ])
    
    # Log security event
    logger.warning(
        f"403 Forbidden: {request.user.username if request.user.is_authenticated else 'anonymous'} "
        f"attempted to access {request.path}",
        extra={
            'security_event': True,
            'event_type': 'access_denied',
            'user_id': request.user.id if request.user.is_authenticated else None,
            'path': request.path,
            'ip_address': get_client_ip(request),
        }
    )
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '403', error_message, 403
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '403', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=403)


@enhanced_error_handler('400')
def error_400(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 400 Bad Request handler with input validation guidance.
    
    Analyzes the request to identify validation issues and provides
    helpful feedback for fixing the problem.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 400
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'Bad request. Please check your input and try again.'
    
    # Try to extract validation details from the exception
    if isinstance(exception, SuspiciousOperation):
        error_message = 'Your request appears to be malformed or suspicious.'
    
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
        ('Help & Documentation', '/help/'),
    ]
    
    # Log suspicious requests
    if isinstance(exception, SuspiciousOperation):
        logger.warning(
            f"Suspicious operation detected: {str(exception)}",
            extra={
                'security_event': True,
                'event_type': 'suspicious_operation',
                'ip_address': get_client_ip(request),
                'path': request.path,
            }
        )
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '400', error_message, 400
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '400', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=400)


@enhanced_error_handler('401')
def error_401(request: HttpRequest, exception: Exception = None) -> HttpResponse:
    """
    Advanced 401 Unauthorized handler for authentication failures.
    
    Handles authentication failures with appropriate redirect logic
    and session management.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 401 (optional)
        
    Returns:
        Rendered error page or JSON response
    """
    if exception is None:
        exception = Exception("Unauthorized")
    
    error_message = 'Authentication is required to access this resource.'
    
    suggestions = [
        ('Login', f'/accounts/login/?next={request.path}'),
        ('Sign Up', '/accounts/signup/'),
        ('Forgot Password', '/accounts/password/reset/'),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '401', error_message, 401
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '401', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=401)


@enhanced_error_handler('429')
def error_429(request: HttpRequest) -> HttpResponse:
    """
    Advanced 429 Too Many Requests handler for rate limiting.
    
    Informs users about rate limits and when they can retry.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Rendered error page or JSON response
    """
    exception = Exception("Too Many Requests")
    error_message = 'You have made too many requests. Please slow down and try again later.'
    
    # Calculate when the user can retry
    retry_after = ErrorHandlerConfig.RATE_LIMIT_WINDOW
    
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        response = build_json_error_response(
            request, exception, '429', error_message, 429
        )
        response['Retry-After'] = str(retry_after)
        return response
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '429', error_message, suggestions
    )
    context['retry_after'] = retry_after
    
    response = render(request, 'app/error.html', context, status=429)
    response['Retry-After'] = str(retry_after)
    
    return response


# ============================================================================
# MIDDLEWARE FOR GLOBAL ERROR HANDLING
# ============================================================================

class EnhancedErrorHandlingMiddleware:
    """
    Middleware that provides global error handling and monitoring.
    
    This middleware catches all unhandled exceptions and provides consistent
    error handling across the application. It should be placed near the top
    of the middleware stack.
    
    Usage:
        Add to settings.py MIDDLEWARE:
        'app.errors.EnhancedErrorHandlingMiddleware',
    """
    
    def __init__(self, get_response):
        """
        Initialize middleware.
        
        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response
    
    def __call__(self, request):
        """
        Process request and catch any unhandled exceptions.
        
        Args:
            request: The HTTP request object
            
        Returns:
            HTTP response
        """
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            # Log the exception
            logger.exception("Unhandled exception in middleware")
            
            # Return appropriate error response
            return self.process_exception(request, e)
    
    def process_exception(self, request, exception):
        """
        Handle exceptions that weren't caught by views.
        
        Args:
            request: The HTTP request object
            exception: The unhandled exception
            
        Returns:
            HTTP response
        """
        # Determine appropriate status code
        if isinstance(exception, PermissionDenied):
            return error_403(request, exception)
        elif isinstance(exception, SuspiciousOperation):
            return error_400(request, exception)
        elif isinstance(exception, BaseApplicationError):
            # Handle custom application errors
            if is_api_request(request):
                return build_json_error_response(
                    request,
                    exception,
                    exception.error_code,
                    exception.user_message,
                    exception.status_code
                )
            
            context = build_error_context(
                request,
                exception,
                str(exception.status_code),
                exception.user_message,
                []
            )
            return render(
                request,
                'app/error.html',
                context,
                status=exception.status_code
            )
        else:
            # Generic 500 error for all other exceptions
            return error_500(request)


# ============================================================================
# HEALTH CHECK & MONITORING ENDPOINTS
# ============================================================================

def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for monitoring systems.
    
    Provides system status information for load balancers,
    monitoring services, and orchestration platforms.
    
    Returns:
        JSON response with health status
    """
    from django.db import connection
    
    status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }
    
    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status['checks']['database'] = 'ok'
    except Exception as e:
        status['status'] = 'unhealthy'
        status['checks']['database'] = f'error: {str(e)}'
    
    # Check cache connectivity
    try:
        cache.set('health_check', 'ok', 10)
        cache.get('health_check')
        status['checks']['cache'] = 'ok'
    except Exception as e:
        status['status'] = 'degraded'
        status['checks']['cache'] = f'error: {str(e)}'
    
    # Return appropriate status code
    status_code = 200 if status['status'] == 'healthy' else 503
    
    return JsonResponse(status, status=status_code)