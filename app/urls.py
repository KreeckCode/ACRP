from django.urls import path
from django.views.generic import TemplateView

from acrp import settings
from . import views

app_name = 'common'

### ========== MAIN WORKSPACE PATTERNS ========== ###

urlpatterns = [
    # Dashboard and main workspace entry points
    path('', views.dashboard, name='dashboard'),
    path('workspace/', views.workspace_dashboard, name='workspace_dashboard'),  # Workspace dashboard
    
    # Kanban board functionality
    path('kanban/', views.kanban_workspace, name='kanban_workspace'),
    path('kanban-board/', views.kanban_workspace, name='kanban_board'),
    # Add this line in the PROJECT MANAGEMENT section:
    path('projects/<uuid:project_id>/kanban/', views.project_kanban, name='project_kanban'),
    
    # Global search and notifications
    path('search/', views.workspace_search, name='workspace_search'),
    path('notifications/', views.notification_center, name='notification_center'),
    
    ### ========== EVENT MANAGEMENT ========== ###
    
    # Event CRUD operations
    path('events/', views.event_list, name='event_list'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/<uuid:pk>/', views.event_detail, name='event_detail'),
    path('events/<uuid:pk>/edit/', views.edit_event, name='edit_event'),
    path('events/<uuid:pk>/delete/', views.delete_event, name='delete_event'),
    
    ### ========== ANNOUNCEMENT SYSTEM ========== ###
    
    # Announcement CRUD operations
    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/create/', views.create_announcement, name='create_announcement'),
    path('announcements/<uuid:pk>/', views.announcement_detail, name='announcement_detail'),
    path('announcements/<uuid:pk>/edit/', views.edit_announcement, name='edit_announcement'),
    path('announcements/<uuid:pk>/delete/', views.delete_announcement, name='delete_announcement'),
    
    ### ========== PROJECT MANAGEMENT ========== ###
    
    # Project CRUD operations (using comprehensive views)
    path('projects/', views.project_list, name='project_list'),  # Uses the comprehensive version
    path('projects/create/', views.create_project, name='create_project'),
    path('projects/<uuid:pk>/', views.project_detail, name='project_detail'),  # Uses comprehensive version
    path('projects/<uuid:pk>/edit/', views.edit_project, name='edit_project'),
    path('projects/<uuid:pk>/delete/', views.delete_project, name='delete_project'),
    
    
    ### ========== TASK MANAGEMENT ========== ###
    
    # Task CRUD operations
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.create_task, name='create_task'),
    path('tasks/<uuid:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<uuid:pk>/edit/', views.edit_task, name='edit_task'),
    path('tasks/<uuid:pk>/delete/', views.delete_task, name='delete_task'),
    
    ### ========== RESOURCE MANAGEMENT ========== ###
    
    # Resource CRUD operations
    path('resources/', views.resource_list, name='resource_list'),
    path('resources/create/', views.create_resource, name='create_resource'),
    path('resources/<uuid:pk>/', views.resource_detail, name='resource_detail'),
    path('resources/<uuid:pk>/edit/', views.edit_resource, name='edit_resource'),
    path('resources/<uuid:pk>/delete/', views.delete_resource, name='delete_resource'),
    
    ### ========== TIME TRACKING SYSTEM ========== ###
    
    # Time tracking dashboard
    path('time-tracking/', views.time_tracking_dashboard, name='time_tracking_dashboard'),
    
    ### ========== AJAX AND API ENDPOINTS ========== ###
    
    # Task management AJAX endpoints
    path('ajax/tasks/create/', views.task_create_ajax, name='task_create_ajax'),
    path('ajax/tasks/<uuid:task_id>/update-status/', views.kanban_update_task_status, name='task_update_status_ajax'),
    path('ajax/tasks/<uuid:pk>/move/', views.move_task, name='move_task'),
    path('ajax/tasks/<uuid:pk>/details/', views.task_detail_ajax, name='task_detail_ajax'),
    
    # Comment system AJAX endpoints
    path('ajax/comments/add/', views.add_comment_ajax, name='add_comment_ajax'),
    
    # Notification AJAX endpoints
    path('ajax/notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    
    ### ========== LEGACY SUPPORT AND ALIASES ========== ###
    
    # Legacy URL redirects for backwards compatibility
    path('legacy/kanban-board/', views.kanban_workspace, name='legacy_kanban_board'),
    path('legacy/project-list/', views.project_list, name='legacy_project_list'),
    
    # Legacy event URLs (using different parameter names for compatibility)
    path('events/<uuid:event_id>/detail/', views.event_detail, name='event_detail_legacy'),
    path('events/<uuid:event_id>/edit/', views.edit_event, name='edit_event_legacy'),
    path('events/<uuid:event_id>/delete/', views.delete_event, name='delete_event_legacy'),
    
    # Legacy announcement URLs
    path('announcements/<uuid:announcement_id>/detail/', views.announcement_detail, name='announcement_detail_legacy'),
    path('announcements/<uuid:announcement_id>/edit/', views.edit_announcement, name='edit_announcement_legacy'),
    path('announcements/<uuid:announcement_id>/delete/', views.delete_announcement, name='delete_announcement_legacy'),
    
    # Legacy project URLs
    path('projects/<uuid:project_id>/detail/', views.project_detail, name='project_detail_legacy'),
    path('projects/<uuid:project_id>/edit/', views.edit_project, name='edit_project_legacy'),
    path('projects/<uuid:project_id>/delete/', views.delete_project, name='delete_project_legacy'),
    
    # Legacy task URLs
    path('tasks/<uuid:task_id>/detail/', views.task_detail, name='task_detail_legacy'),
    path('tasks/<uuid:task_id>/edit/', views.edit_task, name='edit_task_legacy'),
    path('tasks/<uuid:task_id>/delete/', views.delete_task, name='delete_task_legacy'),
    
    # Legacy resource URLs
    path('resources/<uuid:resource_id>/detail/', views.resource_detail, name='resource_detail_legacy'),
    path('resources/<uuid:resource_id>/edit/', views.edit_resource, name='edit_resource_legacy'),
    path('resources/<uuid:resource_id>/delete/', views.delete_resource, name='delete_resource_legacy'),

    
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<uuid:pk>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.notification_mark_all_read, name='notification_mark_all_read'),
    path('notifications/<uuid:pk>/delete/', views.notification_delete, name='notification_delete'),
    path('notifications/fetch/', views.notification_fetch, name='notification_fetch'),
]


# Custom error handlers (configured in main URLs)
handler404 = 'app.views.error_404'
handler500 = 'app.views.error_500'
handler403 = 'app.views.error_403'
handler400 = 'app.views.error_400'
