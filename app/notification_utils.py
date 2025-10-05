import logging
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Notification

logger = logging.getLogger(__name__)


def create_notification(
    recipient,
    notification_type,
    title,
    message,
    content_object=None,
    sender=None,
    action_url='',
    extra_data=None,
    scheduled_for=None,
    expires_at=None
):
    """
    Universal function to create notifications.
    
    Args:
        recipient: User object who will receive the notification
        notification_type: Type from Notification.NOTIFICATION_TYPES
        title: Short title for the notification
        message: Detailed message
        content_object: Optional related object (Project, Task, Event, etc.)
        sender: Optional User who triggered the notification
        action_url: Optional URL to navigate to when clicked
        extra_data: Optional dict with additional data
        scheduled_for: Optional datetime to schedule notification
        expires_at: Optional datetime when notification expires
    
    Returns:
        Notification object or None if creation failed
    
    Example:
        from app.notification_utils import create_notification
        
        # Simple notification
        create_notification(
            recipient=user,
            notification_type='task_assigned',
            title='New Task Assigned',
            message='You have been assigned to "Fix bug #123"'
        )
        
        # With related object and action URL
        create_notification(
            recipient=user,
            notification_type='event_reminder',
            title='Event Starting Soon',
            message=f'Event "{event.title}" starts in 30 minutes',
            content_object=event,
            action_url=event.get_absolute_url(),
            sender=request.user
        )
    """
    try:
        # Validate notification type
        valid_types = [choice[0] for choice in Notification.NOTIFICATION_TYPES]
        if notification_type not in valid_types:
            logger.warning(f"Invalid notification type: {notification_type}")
            return None
        
        # Create notification
        notification = Notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            sender=sender,
            action_url=action_url,
            extra_data=extra_data or {},
            scheduled_for=scheduled_for,
            expires_at=expires_at
        )
        
        # Set content object if provided
        if content_object:
            notification.content_type = ContentType.objects.get_for_model(content_object)
            notification.object_id = content_object.pk
        
        # If not scheduled, mark as delivered
        if not scheduled_for:
            notification.is_delivered = True
            notification.delivered_at = timezone.now()
        
        notification.save()
        
        logger.info(
            f"Notification created: {notification_type} for {recipient.username}"
        )
        
        return notification
        
    except Exception as e:
        logger.error(f"Error creating notification: {e}", exc_info=True)
        return None


def notify_users(
    recipients,
    notification_type,
    title,
    message,
    content_object=None,
    sender=None,
    action_url='',
    extra_data=None
):
    """
    Create notifications for multiple users at once.
    
    Args:
        recipients: List or QuerySet of User objects
        Other args same as create_notification
    
    Returns:
        List of created Notification objects
    
    Example:
        from app.notification_utils import notify_users
        
        # Notify all project team members
        notify_users(
            recipients=project.team_members.all(),
            notification_type='project_updated',
            title='Project Updated',
            message=f'{user.get_full_name()} updated the project timeline',
            content_object=project,
            sender=user
        )
    """
    notifications = []
    
    for recipient in recipients:
        notification = create_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            content_object=content_object,
            sender=sender,
            action_url=action_url,
            extra_data=extra_data
        )
        
        if notification:
            notifications.append(notification)
    
    logger.info(f"Created {len(notifications)} notifications for {len(list(recipients))} recipients")
    
    return notifications


def mark_notification_read(notification_id, user):
    """
    Mark a single notification as read.
    
    Args:
        notification_id: UUID of the notification
        user: User object (for permission check)
    
    Returns:
        Boolean indicating success
    """
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=user,
            is_active=True
        )
        notification.mark_as_read()
        return True
    except Notification.DoesNotExist:
        logger.warning(f"Notification {notification_id} not found for user {user.username}")
        return False
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}")
        return False


def mark_all_read(user):
    """
    Mark all notifications as read for a user.
    
    Args:
        user: User object
    
    Returns:
        Number of notifications marked as read
    """
    try:
        count = Notification.objects.filter(
            recipient=user,
            is_read=False,
            is_active=True
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        logger.info(f"Marked {count} notifications as read for {user.username}")
        return count
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}")
        return 0


def get_unread_count(user):
    """
    Get count of unread notifications for a user.
    
    Args:
        user: User object
    
    Returns:
        Integer count of unread notifications
    """
    try:
        return Notification.objects.filter(
            recipient=user,
            is_read=False,
            is_active=True
        ).count()
    except Exception as e:
        logger.error(f"Error getting unread count: {e}")
        return 0


def get_recent_notifications(user, limit=10):
    """
    Get recent notifications for a user.
    
    Args:
        user: User object
        limit: Maximum number of notifications to return
    
    Returns:
        QuerySet of Notification objects
    """
    return Notification.objects.filter(
        recipient=user,
        is_active=True
    ).select_related(
        'sender', 'content_type'
    ).order_by('-created_at')[:limit]


def delete_notification(notification_id, user):
    """
    Soft delete a notification.
    
    Args:
        notification_id: UUID of the notification
        user: User object (for permission check)
    
    Returns:
        Boolean indicating success
    """
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=user,
            is_active=True
        )
        notification.is_active = False
        notification.save(update_fields=['is_active', 'updated_at'])
        return True
    except Notification.DoesNotExist:
        return False
    except Exception as e:
        logger.error(f"Error deleting notification: {e}")
        return False