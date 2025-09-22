from django.contrib import admin
from .models import (
    # Core Models
    WorkspacePermission,
    
    # Calendar and Event System
    Event,
    EventParticipation,
    
    # Announcement System
    Announcement,
    AnnouncementRead,
    
    # Project Management
    Tag,
    ProjectStatus,
    Projects,
    ProjectMembership,
    Milestone,
    
    # Task Management
    TaskStatus,
    Task,
    TaskAssignment,
    
    # Time Tracking System
    TimeEntry,
    
    # Collaboration System
    Comment,
    CommentLike,
    
    # Attachment System
    Attachment,
    
    # Activity and Audit System
    ActivityLog,
    
    # Notification System
    Notification,
    
    # Resource and Training System
    Resource,
    ResourceRating,
    
    # Quiz and Assessment System
    Quiz,
    Question,
    Answer,
    QuizAttempt,
    QuizResponse,
)

# Core Models
admin.site.register(WorkspacePermission)

# Calendar and Event System
admin.site.register(Event)
admin.site.register(EventParticipation)

# Announcement System
admin.site.register(Announcement)
admin.site.register(AnnouncementRead)

# Project Management
admin.site.register(Tag)
admin.site.register(ProjectStatus)
admin.site.register(Projects)
admin.site.register(ProjectMembership)
admin.site.register(Milestone)

# Task Management
admin.site.register(TaskStatus)
admin.site.register(Task)
admin.site.register(TaskAssignment)

# Time Tracking System
admin.site.register(TimeEntry)

# Collaboration System
admin.site.register(Comment)
admin.site.register(CommentLike)

# Attachment System
admin.site.register(Attachment)

# Activity and Audit System
admin.site.register(ActivityLog)

# Notification System
admin.site.register(Notification)

# Resource and Training System
admin.site.register(Resource)
admin.site.register(ResourceRating)

# Quiz and Assessment System
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Answer)
admin.site.register(QuizAttempt)
admin.site.register(QuizResponse)