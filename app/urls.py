from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Events
    path('events/', views.event_list, name='event_list'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/edit/', views.edit_event, name='edit_event'),
    path('events/<int:event_id>/delete/', views.delete_event, name='delete_event'),

    # Announcements
    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/create/', views.create_announcement, name='create_announcement'),
    path('announcements/<int:announcement_id>/', views.announcement_detail, name='announcement_detail'),
    path('announcements/<int:announcement_id>/edit/', views.edit_announcement, name='edit_announcement'),
    path('announcements/<int:announcement_id>/delete/', views.delete_announcement, name='delete_announcement'),

    # Projects
    path('projects/', views.project_list, name='project_list'),
    path('projects/add/', views.create_project, name='create_project'),
    path('projects/<int:project_id>/edit/', views.edit_project, name='edit_project'),
    path('projects/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    # Kanban view per project
    path('projects/<int:pk>/kanban/', views.project_kanban, name='project_kanban'),

    # Tasks
    path('tasks/add/', views.create_task, name='task_add'),
    path('tasks/<int:pk>/edit/', views.edit_task, name='task_edit'),
    path('tasks/<int:pk>/delete/', views.delete_task, name='task_delete'),
    # AJAX detail and move
    path('tasks/<int:pk>/detail/', views.task_detail_ajax, name='task_detail_ajax'),
    path('tasks/<int:pk>/move/', views.move_task, name='move_task'),

]