import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.db.models import Q, Count, Sum, Avg, F
from django.db import transaction

from .models import (
    ActivityLog, Notification, Projects, Task, Comment, TimeEntry,
    WorkspacePermission, Tag, ProjectMembership
)

User = get_user_model()
logger = logging.getLogger(__name__)

### ========== ACTIVITY LOGGING SYSTEM ========== ###

def log_activity(user: User, action_type: str, content_object: Any, 
                description: str = "", extra_data: Dict = None, 
                related_project: 'Projects' = None, related_task: 'Task' = None,
                request=None) -> ActivityLog:
    """
    Comprehensive activity logging system that tracks all user actions
    across the workspace. Provides detailed audit trails and analytics.
    
    Args:
        user: The user performing the action
        action_type: Type of action (create, update, delete, etc.)
        content_object: The object being acted upon
        description: Human-readable description of the action
        extra_data: Additional metadata as JSON
        related_project: Associated project (auto-detected if not provided)
        related_task: Associated task (auto-detected if not provided)
        request: HTTP request object for IP/user agent capture
    
    Returns:
        ActivityLog instance
    """
    try:
        # Auto-detect related objects if not provided
        if not related_project and hasattr(content_object, 'project'):
            related_project = content_object.project
        elif not related_project and isinstance(content_object, Projects):
            related_project = content_object
            
        if not related_task and isinstance(content_object, Task):
            related_task = content_object
        elif not related_task and hasattr(content_object, 'task'):
            related_task = content_object.task
        
        # Extract request metadata
        ip_address = None
        user_agent = ""
        if request:
            ip_address = get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length
        
        # Create activity log
        activity = ActivityLog.objects.create(
            user=user,
            action_type=action_type,
            description=description or f"{action_type.title()} {content_object._meta.verbose_name}",
            content_type=ContentType.objects.get_for_model(content_object),
            object_id=str(content_object.pk),
            related_project=related_project,
            related_task=related_task,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data or {}
        )
        
        # Update cache for activity feeds
        _invalidate_activity_cache(user, related_project)
        
        return activity
        
    except Exception as e:
        logger.error(f"Failed to log activity: {e}", exc_info=True)
        # Don't raise exception to avoid breaking main functionality
        return None


def get_client_ip(request) -> str:
    """
    Extract client IP address from request, handling proxies and load balancers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def _invalidate_activity_cache(user: User, project: 'Projects' = None):
    """Invalidate relevant activity feed caches."""
    cache_keys = [
        f"activity_feed_user_{user.id}",
        "activity_feed_global",
    ]
    
    if project:
        cache_keys.append(f"activity_feed_project_{project.id}")
    
    cache.delete_many(cache_keys)


def generate_activity_feed(user: User, project: 'Projects' = None, 
                         days: int = 7, limit: int = 50) -> List[Dict]:
    """
    Generate comprehensive activity feed for user or project with intelligent
    filtering and relevance scoring.
    
    Args:
        user: User requesting the feed
        project: Optional project to filter activities
        days: Number of days to look back
        limit: Maximum number of activities to return
    
    Returns:
        List of activity dictionaries with metadata
    """
    cache_key = f"activity_feed_{'project_' + str(project.id) if project else 'user_' + str(user.id)}_{days}_{limit}"
    cached_feed = cache.get(cache_key)
    
    if cached_feed is not None:
        return cached_feed
    
    # Base queryset
    activities = ActivityLog.objects.select_related(
        'user', 'content_type', 'related_project', 'related_task'
    ).filter(
        timestamp__gte=timezone.now() - timedelta(days=days)
    )
    
    # Filter based on user permissions and relevance
    if project:
        # Project-specific feed
        activities = activities.filter(related_project=project)
    else:
        # User's personalized feed
        user_projects = Projects.objects.filter(
            Q(manager=user) | Q(team_members=user),
            is_active=True
        ).values_list('id', flat=True)
        
        activities = activities.filter(
            Q(related_project__id__in=user_projects) |
            Q(user=user) |
            Q(action_type__in=['create', 'complete', 'approve'])  # Always show important actions
        )
    
    # Fetch and enhance activities
    feed_items = []
    for activity in activities.order_by('-timestamp')[:limit]:
        try:
            item = {
                'id': activity.id,
                'user': {
                    'id': activity.user.id,
                    'name': activity.user.get_full_name(),
                    'username': activity.user.username,
                    'avatar_url': get_user_avatar_url(activity.user),
                },
                'action_type': activity.action_type,
                'description': activity.description,
                'timestamp': activity.timestamp,
                'content_type': activity.content_type.model,
                'object_id': activity.object_id,
                'extra_data': activity.extra_data,
                'relevance_score': _calculate_relevance_score(activity, user),
            }
            
            # Add object details if still exists
            try:
                content_object = activity.content_object
                if content_object:
                    item['object'] = {
                        'title': str(content_object),
                        'url': getattr(content_object, 'get_absolute_url', lambda: '#')(),
                    }
            except:
                item['object'] = {'title': 'Deleted object', 'url': '#'}
            
            # Add project context
            if activity.related_project:
                item['project'] = {
                    'id': activity.related_project.id,
                    'name': activity.related_project.name,
                    'code': activity.related_project.code,
                    'url': activity.related_project.get_absolute_url(),
                }
            
            feed_items.append(item)
            
        except Exception as e:
            logger.warning(f"Error processing activity {activity.id}: {e}")
            continue
    
    # Sort by relevance and timestamp
    feed_items.sort(key=lambda x: (x['relevance_score'], x['timestamp']), reverse=True)
    
    # Cache for 5 minutes
    cache.set(cache_key, feed_items, 300)
    
    return feed_items


def _calculate_relevance_score(activity: ActivityLog, user: User) -> float:
    """
    Calculate relevance score for activity based on user relationship
    and action importance.
    """
    score = 0.0
    
    # Base score by action type
    action_scores = {
        'create': 3.0,
        'complete': 5.0,
        'approve': 4.0,
        'assign': 4.0,
        'comment': 2.0,
        'update': 1.0,
        'delete': 2.0,
    }
    score += action_scores.get(activity.action_type, 1.0)
    
    # User relationship bonus
    if activity.user == user:
        score += 2.0  # Own actions
    elif activity.related_project and user in activity.related_project.team_members.all():
        score += 1.5  # Team member actions
    elif activity.related_project and activity.related_project.manager == user:
        score += 1.8  # Actions in managed projects
    
    # Recency bonus (higher score for recent activities)
    hours_ago = (timezone.now() - activity.timestamp).total_seconds() / 3600
    if hours_ago < 1:
        score += 2.0
    elif hours_ago < 6:
        score += 1.0
    elif hours_ago < 24:
        score += 0.5
    
    # Action target bonus
    try:
        content_object = activity.content_object
        if isinstance(content_object, Task) and content_object.assigned_to == user:
            score += 3.0  # Actions on user's tasks
        elif isinstance(content_object, Projects) and content_object.manager == user:
            score += 2.0  # Actions on user's projects
    except:
        pass
    
    return score


### ========== NOTIFICATION SYSTEM ========== ###

def send_notification(recipient: User, notification_type: str, title: str,
                     message: str, content_object: Any = None,
                     action_url: str = "", sender: User = None,
                     delivery_method: str = 'in_app',
                     scheduled_for: datetime = None,
                     extra_data: Dict = None) -> Notification:
    """
    Comprehensive notification system with multiple delivery methods,
    smart batching, and user preferences.
    
    Args:
        recipient: User to receive the notification
        notification_type: Type of notification (task_assigned, etc.)
        title: Notification title
        message: Notification message
        content_object: Object the notification refers to
        action_url: URL to navigate when notification is clicked
        sender: User who triggered the notification
        delivery_method: How to deliver (in_app, email, sms, push)
        scheduled_for: When to send (for delayed notifications)
        extra_data: Additional metadata
    
    Returns:
        Notification instance
    """
    try:
        # Check user notification preferences
        if not _should_send_notification(recipient, notification_type, sender):
            return None
        
        # Create notification
        notification = Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=notification_type,
            title=title,
            message=message,
            content_type=ContentType.objects.get_for_model(content_object) if content_object else None,
            object_id=str(content_object.pk) if content_object else None,
            action_url=action_url,
            delivery_method=delivery_method,
            scheduled_for=scheduled_for or timezone.now(),
            extra_data=extra_data or {}
        )
        
        # Process immediate delivery
        if not scheduled_for or scheduled_for <= timezone.now():
            _deliver_notification(notification)
        
        # Invalidate notification cache
        cache.delete(f"unread_notifications_{recipient.id}")
        
        return notification
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}", exc_info=True)
        return None


def _should_send_notification(recipient: User, notification_type: str, 
                            sender: User = None) -> bool:
    """
    Check user preferences and business rules to determine if notification
    should be sent.
    """
    # Don't send notifications to inactive users
    if not recipient.is_active:
        return False
    
    # Don't send self-notifications (unless explicitly configured)
    if sender == recipient:
        notification_self_types = ['system_alert', 'reminder']
        if notification_type not in notification_self_types:
            return False
    
    # Check user notification preferences (implement based on your user model)
    # This would typically check user profile settings
    
    # Check for recent duplicate notifications (prevent spam)
    recent_duplicate = Notification.objects.filter(
        recipient=recipient,
        notification_type=notification_type,
        sender=sender,
        created_at__gte=timezone.now() - timedelta(minutes=15)
    ).exists()
    
    if recent_duplicate:
        return False
    
    return True


def _deliver_notification(notification: Notification):
    """
    Deliver notification via the specified method.
    """
    try:
        if notification.delivery_method == 'email':
            _send_email_notification(notification)
        elif notification.delivery_method == 'sms':
            _send_sms_notification(notification)
        elif notification.delivery_method == 'push':
            _send_push_notification(notification)
        
        # Mark as delivered
        notification.is_delivered = True
        notification.delivered_at = timezone.now()
        notification.save(update_fields=['is_delivered', 'delivered_at'])
        
    except Exception as e:
        logger.error(f"Failed to deliver notification {notification.id}: {e}")


def _send_email_notification(notification: Notification):
    """Send notification via email with rich HTML template."""
    try:
        context = {
            'notification': notification,
            'recipient': notification.recipient,
            'sender': notification.sender,
            'action_url': f"{settings.SITE_URL}{notification.action_url}" if notification.action_url else "",
            'site_name': getattr(settings, 'SITE_NAME', 'Workspace'),
        }
        
        # Render email templates
        html_content = render_to_string('app/emails/notification.html', context)
        text_content = strip_tags(html_content)
        
        # Create email
        email = EmailMultiAlternatives(
            subject=f"[{context['site_name']}] {notification.title}",
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[notification.recipient.email]
        )
        email.attach_alternative(html_content, "text/html")
        
        # Send email
        email.send()
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        raise


def _send_sms_notification(notification: Notification):
    """Send notification via SMS (implement based on your SMS provider)."""
    # Implement SMS delivery based on your SMS service provider
    pass


def _send_push_notification(notification: Notification):
    """Send push notification (implement based on your push service)."""
    # Implement push notification based on your service (Firebase, etc.)
    pass


def batch_send_notifications(notifications: List[Dict], delay_minutes: int = 0):
    """
    Send multiple notifications efficiently with optional batching delay.
    Useful for bulk operations and digest emails.
    """
    scheduled_time = timezone.now() + timedelta(minutes=delay_minutes) if delay_minutes > 0 else None
    
    created_notifications = []
    for notif_data in notifications:
        notification = send_notification(
            scheduled_for=scheduled_time,
            **notif_data
        )
        if notification:
            created_notifications.append(notification)
    
    return created_notifications


### ========== PERMISSION SYSTEM ========== ###

def check_permission(user: User, permission_type: str, content_object: Any) -> bool:
    """
    Comprehensive permission checking system that handles both Django
    permissions and custom workspace permissions.
    
    Args:
        user: User to check permissions for
        permission_type: Type of permission (view, edit, delete, manage, etc.)
        content_object: Object to check permissions against
    
    Returns:
        Boolean indicating if user has permission
    """
    if not user.is_authenticated:
        return False
    
    # Superusers have all permissions
    if user.is_superuser:
        return True
    
    # Check Django model permissions first
    app_label = content_object._meta.app_label
    model_name = content_object._meta.model_name
    django_perm = f"{app_label}.{permission_type}_{model_name}"
    
    if user.has_perm(django_perm):
        return True
    
    # Check custom workspace permissions
    content_type = ContentType.objects.get_for_model(content_object)
    
    has_workspace_perm = WorkspacePermission.objects.filter(
        user=user,
        permission_type=permission_type,
        content_type=content_type,
        object_id=str(content_object.pk)
    ).exists()
    
    if has_workspace_perm:
        return True
    
    # Object-specific permission checks
    if isinstance(content_object, Projects):
        return _check_project_permission(user, permission_type, content_object)
    elif isinstance(content_object, Task):
        return _check_task_permission(user, permission_type, content_object)
    elif isinstance(content_object, Comment):
        return _check_comment_permission(user, permission_type, content_object)
    
    return False


def _check_project_permission(user: User, permission_type: str, project: 'Projects') -> bool:
    """Check project-specific permissions."""
    # Project manager has all permissions
    if project.manager == user:
        return True
    
    # Team members have view and limited edit permissions
    if user in project.team_members.all():
        membership = ProjectMembership.objects.filter(
            project=project, user=user, is_active=True
        ).first()
        
        if membership:
            if permission_type == 'view':
                return True
            elif permission_type in ['edit', 'comment'] and membership.role in ['lead', 'coordinator']:
                return True
            elif permission_type == 'manage_tasks' and membership.can_manage_tasks:
                return True
            elif permission_type == 'invite_members' and membership.can_invite_members:
                return True
    
    # Public projects allow viewing
    if permission_type == 'view' and project.is_public:
        return True
    
    return False


def _check_task_permission(user: User, permission_type: str, task: 'Task') -> bool:
    """Check task-specific permissions."""
    # Task assignee can view and edit
    if task.assigned_to == user:
        return permission_type in ['view', 'edit', 'comment']
    
    # Task creator can manage
    if task.created_by == user:
        return permission_type in ['view', 'edit', 'delete', 'comment']
    
    # Check project permissions
    return _check_project_permission(user, permission_type, task.project)


def _check_comment_permission(user: User, permission_type: str, comment: Comment) -> bool:
    """Check comment-specific permissions."""
    # Comment author can edit/delete
    if comment.author == user:
        return permission_type in ['view', 'edit', 'delete']
    
    # Check permissions on the commented object
    try:
        content_object = comment.content_object
        if content_object:
            return check_permission(user, 'view', content_object)
    except:
        pass
    
    return False


### ========== ANALYTICS AND REPORTING ========== ###

def get_user_workload(user: User, date_range: int = 30) -> Dict:
    """
    Calculate comprehensive user workload metrics including tasks,
    time utilization, and productivity indicators.
    
    Args:
        user: User to analyze
        date_range: Number of days to analyze
    
    Returns:
        Dictionary with workload metrics
    """
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=date_range)
    
    # Task metrics
    user_tasks = Task.objects.filter(assigned_to=user, is_active=True)
    
    task_metrics = {
        'total_active': user_tasks.count(),
        'overdue': user_tasks.filter(
            due_date__lt=end_date,
            status__is_final=False
        ).count(),
        'due_this_week': user_tasks.filter(
            due_date__range=[end_date, end_date + timedelta(days=7)],
            status__is_final=False
        ).count(),
        'completed_in_period': user_tasks.filter(
            completed_date__date__range=[start_date, end_date],
            status__is_final=True
        ).count(),
        'high_priority': user_tasks.filter(
            priority__lte=2,
            status__is_final=False
        ).count(),
    }
    
    # Time tracking metrics
    time_entries = TimeEntry.objects.filter(
        user=user,
        start_time__date__range=[start_date, end_date],
        is_active=True
    )
    
    time_metrics = time_entries.aggregate(
        total_hours=Sum('duration_minutes'),
        billable_hours=Sum('duration_minutes', filter=Q(is_billable=True)),
        project_count=Count('project', distinct=True),
        avg_daily_hours=Avg('duration_minutes')
    )
    
    # Convert minutes to hours
    for key in ['total_hours', 'billable_hours', 'avg_daily_hours']:
        if time_metrics[key]:
            time_metrics[key] = round(time_metrics[key] / 60, 1)
        else:
            time_metrics[key] = 0
    
    # Project involvement
    project_metrics = {
        'managed_projects': Projects.objects.filter(
            manager=user, is_active=True
        ).count(),
        'team_projects': Projects.objects.filter(
            team_members=user, is_active=True
        ).count(),
    }
    
    # Productivity indicators
    productivity_score = _calculate_productivity_score(
        task_metrics, time_metrics, date_range
    )
    
    return {
        'tasks': task_metrics,
        'time': time_metrics,
        'projects': project_metrics,
        'productivity_score': productivity_score,
        'workload_level': _categorize_workload(task_metrics, time_metrics),
        'recommendations': _generate_workload_recommendations(
            task_metrics, time_metrics, productivity_score
        )
    }


def _calculate_productivity_score(task_metrics: Dict, time_metrics: Dict, days: int) -> float:
    """Calculate a productivity score (0-100) based on various metrics."""
    score = 50.0  # Base score
    
    # Task completion rate
    if task_metrics['total_active'] > 0:
        completion_rate = task_metrics['completed_in_period'] / days * 7  # Weekly rate
        score += min(completion_rate * 10, 30)
    
    # Overdue penalty
    if task_metrics['total_active'] > 0:
        overdue_ratio = task_metrics['overdue'] / task_metrics['total_active']
        score -= overdue_ratio * 20
    
    # Time utilization (assuming 40 hours/week as baseline)
    expected_hours = (days / 7) * 40
    if time_metrics['total_hours'] > 0:
        utilization = min(time_metrics['total_hours'] / expected_hours, 1.5)
        if 0.8 <= utilization <= 1.2:  # Optimal range
            score += 20
        elif utilization > 1.2:  # Overworked
            score += 10
        else:  # Underutilized
            score += utilization * 20
    
    return max(0, min(100, score))


def _categorize_workload(task_metrics: Dict, time_metrics: Dict) -> str:
    """Categorize user workload level."""
    # Simple heuristic based on tasks and time
    active_tasks = task_metrics['total_active']
    weekly_hours = time_metrics['total_hours']
    overdue_tasks = task_metrics['overdue']
    
    if overdue_tasks > 5 or weekly_hours > 50:
        return 'overloaded'
    elif active_tasks > 15 or weekly_hours > 40:
        return 'high'
    elif active_tasks > 8 or weekly_hours > 25:
        return 'moderate'
    elif active_tasks > 3 or weekly_hours > 10:
        return 'light'
    else:
        return 'minimal'


def _generate_workload_recommendations(task_metrics: Dict, time_metrics: Dict, 
                                     productivity_score: float) -> List[str]:
    """Generate actionable workload recommendations."""
    recommendations = []
    
    if task_metrics['overdue'] > 0:
        recommendations.append(
            f"Address {task_metrics['overdue']} overdue tasks to improve timeline compliance"
        )
    
    if task_metrics['high_priority'] > 5:
        recommendations.append(
            "Consider delegating some high-priority tasks to balance workload"
        )
    
    if time_metrics['total_hours'] > 50:
        recommendations.append(
            "Weekly hours exceed healthy limits - consider workload redistribution"
        )
    
    if productivity_score < 60:
        recommendations.append(
            "Focus on completing existing tasks before taking on new assignments"
        )
    
    if time_metrics['total_hours'] < 20 and task_metrics['total_active'] < 5:
        recommendations.append(
            "Capacity available for additional responsibilities"
        )
    
    return recommendations


def calculate_project_health(project: 'Projects') -> Dict:
    """
    Calculate comprehensive project health metrics including timeline,
    budget, team performance, and risk indicators.
    """
    now = timezone.now().date()
    
    # Timeline health
    total_days = (project.planned_end_date - project.start_date).days
    elapsed_days = (now - project.start_date).days
    timeline_progress = (elapsed_days / total_days * 100) if total_days > 0 else 0
    
    # Task completion health
    tasks = project.tasks.filter(is_active=True)
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status__is_final=True).count()
    task_progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # Budget health
    budget_health = {
        'allocated': float(project.budget_allocated or 0),
        'spent': float(project.budget_spent or 0),
        'utilization': project.get_budget_utilization(),
        'status': 'healthy'
    }
    
    if budget_health['utilization'] > 90:
        budget_health['status'] = 'critical'
    elif budget_health['utilization'] > 75:
        budget_health['status'] = 'warning'
    
    # Team health
    team_metrics = ProjectMembership.objects.filter(
        project=project, is_active=True
    ).aggregate(
        total_members=Count('id'),
        active_members=Count('id', filter=Q(user__last_login__gte=now - timedelta(days=7)))
    )
    
    team_health = {
        'size': team_metrics['total_members'],
        'active_ratio': (team_metrics['active_members'] / max(team_metrics['total_members'], 1)),
        'workload_distribution': _analyze_team_workload(project)
    }
    
    # Risk indicators
    risks = []
    if timeline_progress > task_progress + 10:
        risks.append('behind_schedule')
    if budget_health['utilization'] > 85:
        risks.append('over_budget')
    if team_health['active_ratio'] < 0.7:
        risks.append('low_engagement')
    
    overdue_tasks = tasks.filter(
        due_date__lt=now,
        status__is_final=False
    ).count()
    if overdue_tasks > total_tasks * 0.2:  # More than 20% overdue
        risks.append('task_delays')
    
    # Overall health score
    health_score = _calculate_overall_health_score(
        timeline_progress, task_progress, budget_health, team_health, risks
    )
    
    return {
        'timeline': {
            'progress': round(timeline_progress, 1),
            'task_progress': round(task_progress, 1),
            'deviation': round(timeline_progress - task_progress, 1)
        },
        'budget': budget_health,
        'team': team_health,
        'risks': risks,
        'health_score': health_score,
        'status': _get_health_status(health_score),
        'recommendations': _generate_project_recommendations(
            timeline_progress, task_progress, budget_health, team_health, risks
        )
    }


def _analyze_team_workload(project: 'Projects') -> Dict:
    """Analyze workload distribution across team members."""
    members = project.team_members.all()
    workloads = []
    
    for member in members:
        active_tasks = member.assigned_tasks.filter(
            project=project,
            status__is_final=False,
            is_active=True
        ).count()
        workloads.append(active_tasks)
    
    if not workloads:
        return {'balance_score': 100, 'distribution': 'even'}
    
    avg_workload = sum(workloads) / len(workloads)
    variance = sum((w - avg_workload) ** 2 for w in workloads) / len(workloads)
    
    # Balance score (100 = perfectly balanced)
    balance_score = max(0, 100 - variance * 10)
    
    distribution = 'even'
    if variance > 4:
        distribution = 'uneven'
    elif variance > 2:
        distribution = 'moderate'
    
    return {
        'balance_score': round(balance_score, 1),
        'distribution': distribution,
        'average_tasks': round(avg_workload, 1)
    }


def _calculate_overall_health_score(timeline_progress: float, task_progress: float,
                                   budget_health: Dict, team_health: Dict,
                                   risks: List[str]) -> float:
    """Calculate overall project health score (0-100)."""
    score = 100.0
    
    # Timeline penalty
    timeline_deviation = abs(timeline_progress - task_progress)
    score -= min(timeline_deviation * 2, 30)
    
    # Budget penalty
    if budget_health['utilization'] > 100:
        score -= 20
    elif budget_health['utilization'] > 85:
        score -= 10
    
    # Team penalty
    score -= (1 - team_health['active_ratio']) * 15
    
    # Risk penalties
    risk_penalties = {
        'behind_schedule': 15,
        'over_budget': 20,
        'low_engagement': 10,
        'task_delays': 15
    }
    
    for risk in risks:
        score -= risk_penalties.get(risk, 5)
    
    return max(0, min(100, score))


def _get_health_status(score: float) -> str:
    """Convert health score to status category."""
    if score >= 85:
        return 'excellent'
    elif score >= 70:
        return 'good'
    elif score >= 55:
        return 'fair'
    elif score >= 40:
        return 'poor'
    else:
        return 'critical'


def _generate_project_recommendations(timeline_progress: float, task_progress: float,
                                    budget_health: Dict, team_health: Dict,
                                    risks: List[str]) -> List[str]:
    """Generate actionable project improvement recommendations."""
    recommendations = []
    
    if 'behind_schedule' in risks:
        recommendations.append(
            "Consider adding resources or reducing scope to meet timeline"
        )
    
    if 'over_budget' in risks:
        recommendations.append(
            "Review budget allocation and consider cost optimization measures"
        )
    
    if team_health['workload_distribution']['distribution'] == 'uneven':
        recommendations.append(
            "Redistribute tasks to balance team workload more effectively"
        )
    
    if 'low_engagement' in risks:
        recommendations.append(
            "Schedule team check-ins to address potential blockers or concerns"
        )
    
    if timeline_progress > task_progress + 20:
        recommendations.append(
            "Accelerate task completion or adjust project timeline expectations"
        )
    
    return recommendations


### ========== UTILITY HELPER FUNCTIONS ========== ###

def get_user_avatar_url(user: User) -> str:
    """Get user avatar URL with fallback to default."""
    if hasattr(user, 'profile') and hasattr(user.profile, 'avatar') and user.profile.avatar:
        return user.profile.avatar.url
    
    # Fallback to Gravatar or default
    if user.email:
        import hashlib
        email_hash = hashlib.md5(user.email.lower().encode()).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon&s=40"
    
    return "/static/images/default-avatar.png"


def generate_cache_key(*args) -> str:
    """Generate consistent cache key from arguments."""
    key_string = "_".join(str(arg) for arg in args)
    return hashlib.md5(key_string.encode()).hexdigest()


def safe_json_loads(data: str, default=None) -> Any:
    """Safely load JSON data with fallback."""
    try:
        return json.loads(data) if data else default
    except (json.JSONDecodeError, TypeError):
        return default


def format_duration(minutes: int) -> str:
    """Format duration in minutes to human-readable string."""
    if minutes < 60:
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {remaining_minutes}m"


def get_next_business_day(date: datetime.date, days: int = 1) -> datetime.date:
    """Get next business day (skipping weekends)."""
    current = date
    days_added = 0
    
    while days_added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            days_added += 1
    
    return current


def truncate_text(text: str, length: int = 100, suffix: str = "...") -> str:
    """Truncate text to specified length with suffix."""
    if len(text) <= length:
        return text
    return text[:length - len(suffix)] + suffix


def validate_email_list(email_string: str) -> List[str]:
    """Validate and extract email addresses from comma-separated string."""
    import re
    
    if not email_string:
        return []
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    emails = [email.strip() for email in email_string.split(',')]
    valid_emails = []
    
    for email in emails:
        if email and re.match(email_pattern, email):
            valid_emails.append(email)
    
    return valid_emails


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file system storage."""
    import re
    
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]
    
    return filename or 'unnamed_file'