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
    user = request.user
    
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
        
        # Calculate total hours (use hours_awarded if available, otherwise hours_claimed)
        total_hours = 0
        for record in approved_records:
            total_hours += float(record.hours_awarded or record.hours_claimed or 0)
        
        stats['cpd_hours'] = total_hours
        
    except (ImportError, AttributeError):
        stats['cpd_hours'] = 0
    
    # Active Members (approximation based on active cards or approved applications)
    stats['active_members'] = stats['active_cards'] or stats['approved_applications']
    stats['new_members'] = 0  # You can calculate this based on recent approvals
    
    # ============================================================================
    # CORE CONTENT (Existing functionality)
    # ============================================================================
    
    # Urgent announcements
    announcements = Announcement.objects.filter(is_urgent=True).order_by('-published_at')[:5]
    
    # Mandatory events
    events = Event.objects.filter(
        is_mandatory=True,
        start_time__gte=timezone.now()
    ).order_by('start_time')[:5]
    
    # User's projects
    projects = Projects.objects.filter(
        manager=user
    ).order_by('-start_date')[:5]
    
    # ============================================================================
    # ITEMS REQUIRING ATTENTION
    # ============================================================================
    
    pending_items = []
    
    # Add role-based pending items
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
                    'url': f"/enrollments/applications/",  # Generic link
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
    
    # CPD requirements for current user
    try:
        # Check if user needs CPD hours
        required_hours = 20  # Annual requirement
        if stats['cpd_hours'] < required_hours:
            pending_items.append({
                'type': 'cpd',
                'title': 'CPD Hours Required',
                'description': f"You need {required_hours - stats['cpd_hours']} more CPD hours this year",
                'created': timezone.now(),
                'url': '/cpd/activities/',
            })
    except:
        pass
    
    # ============================================================================
    # ROLE-BASED CUSTOMIZATION
    # ============================================================================
    
    # Add role-specific context
    role = getattr(user, 'role', None)
    user_role = getattr(role, 'title', 'Member') if role else 'Member'
    
    # Admin-specific stats
    if user.is_staff:
        stats['system_health'] = 99  # You can calculate this based on system metrics
        
        # Recent activities for admins
        try:
            recent_activities = []
            
            # Recent applications
            for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                recent_apps = model.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).order_by('-created_at')[:3]
                
                for app in recent_apps:
                    recent_activities.append({
                        'description': f"New {model.__name__.replace('Application', '')} application from {app.full_names}",
                        'timestamp': app.created_at,
                    })
            
            # Sort by timestamp
            recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
            stats['recent_activities'] = recent_activities[:5]
            
        except:
            stats['recent_activities'] = []
    
    # ============================================================================
    # CONTEXT ASSEMBLY
    # ============================================================================
    
    context = {
        # Core content
        'announcements': announcements,
        'events': events,
        'projects': projects,
        
        # Statistics
        'stats': stats,
        
        # Attention items
        'pending_items': pending_items,
        
        # User context
        'user_role': user_role,
        'is_admin': user.is_staff,
        
        # System status
        'system_status': {
            'card_service': 'operational',
            'email_service': 'operational', 
            'verification_service': 'operational',
        }
    }
    
    return render(request, 'app/dashboard.html', context)




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
        'mentions': mentions,
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


### ========== ERROR HANDLERS ========== ###

def error_404(request, exception):
    """Custom 404 error handler with helpful navigation."""
    context = {
        'error_code': '404',
        'error_message': 'The page you are looking for could not be found.',
        'suggestions': [
            ('Dashboard', '/app/dashboard/'),
            ('Projects', '/app/projects/'),
            ('Tasks', '/app/tasks/'),
            ('Kanban Board', '/app/kanban/'),
        ]
    }
    return render(request, 'app/error.html', context, status=404)


def error_500(request):
    """Custom 500 error handler with error reporting."""
    context = {
        'error_code': '500',
        'error_message': 'An internal server error occurred. Our team has been notified.',
        'suggestions': [
            ('Dashboard', '/app/dashboard/'),
            ('Contact Support', '/support/'),
        ]
    }
    return render(request, 'app/error.html', context, status=500)


def error_403(request, exception):
    """Custom 403 error handler with permission guidance."""
    context = {
        'error_code': '403',
        'error_message': 'You do not have permission to access this resource.',
        'suggestions': [
            ('Dashboard', '/app/dashboard/'),
            ('My Projects', '/app/projects/?filter=my'),
            ('Contact Administrator', '/admin/'),
        ]
    }
    return render(request, 'app/error.html', context, status=403)


def error_400(request, exception):
    """Custom 400 error handler for bad requests."""
    context = {
        'error_code': '400',
        'error_message': 'Bad request. Please check your input and try again.',
        'suggestions': [
            ('Dashboard', '/app/dashboard/'),
            ('Help', '/help/'),
        ]
    }
    return render(request, 'app/error.html', context, status=400)







@login_required
def event_list(request):
    events = Event.objects.all()
    
    # Handle filters
    query = request.GET.get('q', '')
    status = request.GET.get('status', '')
    mandatory = request.GET.get('mandatory', '')
    
    if query:
        events = events.filter(title__icontains=query)
    
    if status == 'upcoming':
        events = events.filter(start_time__gte=timezone.now())
    elif status == 'past':
        events = events.filter(start_time__lt=timezone.now())
    elif status == 'today':
        today = timezone.now().date()
        events = events.filter(start_time__date=today)
    
    if mandatory == 'mandatory':
        events = events.filter(is_mandatory=True)
    elif mandatory == 'optional':
        events = events.filter(is_mandatory=False)
    
    return render(request, 'app/event_list.html', {'events': events})


@login_required
@permission_required('apps.manage_events', raise_exception=True)
def create_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            form.save_m2m()  # for participants
            messages.success(request, 'Event created successfully.')
            return redirect('common:event_list')
    else:
        form = EventForm()
    return render(request, 'app/event_form.html', {'form': form})

@login_required
def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    return render(request, 'app/event_detail.html', {'event': event})

@login_required
@permission_required('apps.manage_events', raise_exception=True)
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully.')
            return redirect('common:event_detail', event_id=event.id)
    else:
        form = EventForm(instance=event)
    return render(request, 'app/event_form.html', {'form': form, 'event': event})

@login_required
@permission_required('apps.manage_events', raise_exception=True)
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        event.delete()
        messages.success(request, 'Event deleted successfully.')
        return redirect('common:event_list')
    return render(request, 'app/confirm_delete.html', {
        'object': event, 'type': 'Event',
        'cancel_url': 'event_detail', 'cancel_id': event.id
    })


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
            ann.posted_by = request.user
            ann.save()
            messages.success(request, 'Announcement posted successfully.')
            return redirect('common:announcement_list')
    else:
        form = AnnouncementForm()
    return render(request, 'app/announcement_form.html', {'form': form})

@login_required
def announcement_detail(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    return render(request, 'app/announcement_detail.html', {'announcement': announcement})

@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def edit_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated successfully.')
            return redirect('common:announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, 'app/announcement_form.html', {'form': form})

@login_required
@permission_required('app.manage_announcements', raise_exception=True)
def delete_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    if request.method == 'POST':
        announcement.delete()
        messages.success(request, 'Announcement deleted successfully.')
        return redirect('common:announcement_list')
    return render(request, 'app/confirm_delete.html', {
        'object': announcement, 'type': 'Announcement',
        'cancel_url': 'announcement_detail', 'cancel_id': announcement.id
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


