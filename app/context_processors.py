from .notification_utils import get_unread_count, get_recent_notifications


def notifications(request):
    """
    Add notification data to template context.
    Available in all templates as: {{ unread_notifications_count }} and {{ recent_notifications }}
    """
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': get_unread_count(request.user),
            'recent_notifications': get_recent_notifications(request.user, limit=5),
        }
    return {
        'unread_notifications_count': 0,
        'recent_notifications': [],
    }