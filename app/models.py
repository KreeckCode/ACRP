from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
import uuid

User = get_user_model()

### ========== CORE WORKSPACE MODELS ========== ###

class BaseModel(models.Model):
    """
    Abstract base model providing common fields for all workspace entities.
    Includes audit trail and soft delete functionality.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name="%(class)s_created",
        db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        abstract = True
        ordering = ['-updated_at']


class WorkspacePermission(models.Model):
    """
    Granular permission system for workspace actions.
    Allows fine-grained control over who can do what.
    """
    PERMISSION_TYPES = [
        ('view', 'View'),
        ('create', 'Create'),
        ('edit', 'Edit'),
        ('delete', 'Delete'),
        ('manage', 'Manage'),  # Full control
        ('comment', 'Comment'),
        ('assign', 'Assign Tasks'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspace_permissions')
    permission_type = models.CharField(max_length=20, choices=PERMISSION_TYPES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='granted_permissions')
    granted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'permission_type', 'content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'permission_type']),
        ]


### ========== EVENT SYSTEM ========== ###

class Event(BaseModel):
    """
    Enhanced event model with recurrence, reminders, and attendance tracking.
    Supports both one-time and recurring events with flexible configuration.
    """
    
    RECURRENCE_TYPES = [
        ('none', 'No Recurrence'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    EVENT_TYPES = [
        ('meeting', 'Meeting'),
        ('deadline', 'Deadline'),
        ('milestone', 'Milestone'),
        ('training', 'Training'),
        ('review', 'Review'),
        ('social', 'Social Event'),
    ]
    
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=300, blank=True)
    virtual_link = models.URLField(blank=True, help_text="Zoom, Teams, or other meeting link")
    
    # Timing and recurrence
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    timezone = models.CharField(max_length=50, default='UTC')
    is_all_day = models.BooleanField(default=False)
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_TYPES, default='none')
    recurrence_interval = models.PositiveIntegerField(default=1, help_text="Every X days/weeks/months")
    recurrence_end_date = models.DateField(null=True, blank=True)
    
    # Event properties
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='meeting')
    is_mandatory = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True, help_text="Visible to all workspace members")
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    
    # Relationships
    participants = models.ManyToManyField(
        User, 
        through='EventParticipation',
        related_name="event_participations", 
        blank=True
    )
    related_project = models.ForeignKey(
        'Projects', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='events'
    )
    related_tasks = models.ManyToManyField('Task', blank=True, related_name='events')
    
    # Metadata
    tags = models.ManyToManyField('Tag', blank=True, related_name='events')
    attachments = models.ManyToManyField('Attachment', blank=True, related_name='events')
    
    def __str__(self):
        return f"{self.title} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"
    
    def is_upcoming(self):
        """Check if event is in the future."""
        return self.start_time > timezone.now()
    
    def get_duration(self):
        """Get event duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)
    
    def get_absolute_url(self):
        return reverse('common:event_detail', kwargs={'pk': self.pk})
    
    class Meta:
        permissions = [
            ("manage_events", "Can create, update, and delete events"),
            ("view_all_events", "Can view all events regardless of participation"),
        ]
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['event_type', 'is_mandatory']),
        ]


class EventParticipation(models.Model):
    """
    Through model for event participation with RSVP status and attendance tracking.
    """
    RSVP_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('tentative', 'Tentative'),
    ]
    
    ATTENDANCE_CHOICES = [
        ('unknown', 'Unknown'),
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rsvp_status = models.CharField(max_length=20, choices=RSVP_CHOICES, default='pending')
    attendance_status = models.CharField(max_length=20, choices=ATTENDANCE_CHOICES, default='unknown')
    rsvp_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['event', 'user']


### ========== ENHANCED ANNOUNCEMENT SYSTEM ========== ###

class Announcement(BaseModel):
    """
    Enhanced announcement system with categorization, targeting, and engagement tracking.
    """
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical'),
    ]
    
    ANNOUNCEMENT_TYPES = [
        ('general', 'General'),
        ('policy', 'Policy Update'),
        ('system', 'System Notification'),
        ('event', 'Event Announcement'),
        ('achievement', 'Achievement'),
        ('alert', 'Alert'),
    ]
    
    title = models.CharField(max_length=200, db_index=True)
    content = models.TextField()
    summary = models.CharField(max_length=500, blank=True, help_text="Brief summary for notifications")
    
    # Classification and targeting
    announcement_type = models.CharField(max_length=20, choices=ANNOUNCEMENT_TYPES, default='general')
    priority = models.CharField(max_length=20, choices=PRIORITY_LEVELS, default='normal')
    
    # Legacy field aliases for backward compatibility with views
    @property
    def date_posted(self):
        """Alias for created_at to maintain compatibility with legacy views"""
        return self.created_at
    
    @property 
    def posted_by(self):
        """Alias for created_by to maintain compatibility with legacy views"""
        return self.created_by
    
    # Publishing and expiry
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Engagement tracking
    read_by = models.ManyToManyField(User, through='AnnouncementRead', related_name='read_announcements')
    
    # Metadata
    tags = models.ManyToManyField('Tag', blank=True, related_name='announcements')
    attachments = models.ManyToManyField('Attachment', blank=True, related_name='announcements')
    
    def __str__(self):
        return self.title
    
    def is_published(self):
        """Check if announcement is currently published."""
        now = timezone.now()
        return (
            self.published_at and 
            self.published_at <= now and 
            (not self.expires_at or self.expires_at > now)
        )
    
    def has_expired(self):
        """Check if announcement has expired."""
        return self.expires_at and timezone.now() > self.expires_at
    
    def get_read_percentage(self):
        """Calculate what percentage of target audience has read this."""
        total_targets = User.objects.filter(is_active=True).count()
        read_count = self.read_by.count()
        return (read_count / total_targets * 100) if total_targets > 0 else 0
    
    def get_absolute_url(self):
        return reverse('common:announcement_detail', kwargs={'pk': self.pk})
    
    class Meta:
        permissions = [
            ("manage_announcements", "Can create, update, and delete announcements"),
            ("publish_announcements", "Can publish and unpublish announcements"),
        ]
        indexes = [
            models.Index(fields=['priority', 'published_at']),
            models.Index(fields=['announcement_type', 'is_urgent']),
        ]


class AnnouncementRead(models.Model):
    """Track when users read announcements."""
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['announcement', 'user']


### ========== ENHANCED PROJECT MANAGEMENT ========== ###

class Tag(BaseModel):
    """
    Enhanced tag system with hierarchical organization and usage analytics.
    """
    name = models.CharField(max_length=50, unique=True, db_index=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1', help_text="Hex color code")
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    usage_count = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    def get_full_name(self):
        """Get full hierarchical name (parent > child)."""
        if self.parent:
            return f"{self.parent.get_full_name()} > {self.name}"
        return self.name
    
    class Meta:
        ordering = ['-usage_count', 'name']


class ProjectStatus(models.Model):
    """
    Customizable project status workflow.
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_initial = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name}"
    
    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Project Statuses'


class Projects(BaseModel):
    """
    Enhanced project model with comprehensive tracking, budgeting, and workflow management.
    """
    
    PRIORITY_LEVELS = [
        (1, 'Critical'),
        (2, 'High'),
        (3, 'Medium'),
        (4, 'Low'),
    ]
    
    # Basic information
    name = models.CharField(max_length=200, db_index=True)
    code = models.CharField(max_length=20, unique=True, help_text="Unique project identifier")
    description = models.TextField()
    objectives = models.TextField(blank=True, help_text="Project objectives and success criteria")
    
    # Timeline and milestones
    start_date = models.DateField(db_index=True)
    planned_end_date = models.DateField(db_index=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Status and workflow
    status = models.ForeignKey(ProjectStatus, on_delete=models.PROTECT, default=1)
    priority = models.IntegerField(choices=PRIORITY_LEVELS, default=3, db_index=True)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Team and responsibilities
    manager = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name="managed_projects",
        help_text="Primary project manager"
    )
    team_members = models.ManyToManyField(
        User, 
        through='ProjectMembership',
        related_name="projects", 
        blank=True
    )
    client = models.CharField(max_length=200, blank=True, help_text="External client or department")
    
    # Budget and resources
    budget_allocated = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    budget_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    estimated_hours = models.PositiveIntegerField(null=True, blank=True)
    actual_hours = models.PositiveIntegerField(default=0)
    
    # Organization and metadata
    tags = models.ManyToManyField(Tag, blank=True, related_name="projects")
    parent_project = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subprojects')
    
    # Visibility and access
    is_public = models.BooleanField(default=True, help_text="Visible to all workspace members")
    is_archived = models.BooleanField(default=False, db_index=True)
    
    def __str__(self):
        return f"[{self.code}] {self.name}"
    
    def get_completion_percentage(self):
        """Calculate completion based on completed tasks."""
        total_tasks = self.tasks.count()
        if total_tasks == 0:
            return 0
        completed_tasks = self.tasks.filter(status__is_final=True).count()
        return (completed_tasks / total_tasks) * 100
    
    def get_budget_utilization(self):
        """Calculate budget utilization percentage."""
        if not self.budget_allocated or self.budget_allocated == 0:
            return 0
        return (self.budget_spent / self.budget_allocated) * 100
    
    def is_overdue(self):
        """Check if project is past its planned end date."""
        return (
            not self.actual_end_date and 
            self.planned_end_date < timezone.now().date() and
            not self.status.is_final
        )
    
    def get_team_size(self):
        """Get total number of team members."""
        return self.team_members.count()
    
    def get_absolute_url(self):
        return reverse('common:project_detail', kwargs={'pk': self.pk})
    
    class Meta:
        permissions = [
            ("manage_projects", "Can create, update, and delete projects"),
            ("view_all_projects", "Can view all projects regardless of membership"),
            ("manage_project_budget", "Can manage project budgets"),
        ]
        indexes = [
            models.Index(fields=['start_date', 'planned_end_date']),
            models.Index(fields=['priority', 'status']),
            models.Index(fields=['is_archived', 'is_public']),
        ]


class ProjectMembership(models.Model):
    """
    Through model for project team membership with roles and permissions.
    """
    PROJECT_ROLES = [
        ('member', 'Team Member'),
        ('lead', 'Team Lead'),
        ('coordinator', 'Coordinator'),
        ('reviewer', 'Reviewer'),
        ('observer', 'Observer'),
    ]
    
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=PROJECT_ROLES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    can_manage_tasks = models.BooleanField(default=False)
    can_invite_members = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['project', 'user']
        indexes = [
            models.Index(fields=['project', 'is_active']),
        ]


class Milestone(BaseModel):
    """
    Project milestones with deliverables and progress tracking.
    """
    
    MILESTONE_TYPES = [
        ('deliverable', 'Deliverable'),
        ('checkpoint', 'Checkpoint'),
        ('review', 'Review'),
        ('approval', 'Approval'),
        ('launch', 'Launch'),
    ]
    
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='milestones')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    milestone_type = models.CharField(max_length=20, choices=MILESTONE_TYPES, default='deliverable')
    
    # Timeline
    planned_date = models.DateField()
    actual_date = models.DateField(null=True, blank=True)
    
    # Status and completion
    is_completed = models.BooleanField(default=False)
    completion_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Dependencies
    dependencies = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='dependents')
    
    # Metadata
    tags = models.ManyToManyField(Tag, blank=True, related_name='milestones')
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"
    
    def is_overdue(self):
        """Check if milestone is overdue."""
        return not self.is_completed and self.planned_date < timezone.now().date()
    
    class Meta:
        ordering = ['planned_date']
        indexes = [
            models.Index(fields=['project', 'planned_date']),
            models.Index(fields=['is_completed', 'planned_date']),
        ]


### ========== ENHANCED TASK MANAGEMENT ========== ###

class TaskStatus(models.Model):
    """
    Customizable task status workflow.
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_initial = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Task Statuses'


class Task(BaseModel):
    """
    Enhanced task model with dependencies, time tracking, and comprehensive workflow.
    """
    
    PRIORITY_LEVELS = [
        (1, 'Critical'),
        (2, 'High'),
        (3, 'Medium'),
        (4, 'Low'),
    ]
    
    TASK_TYPES = [
        ('task', 'Task'),
        ('bug', 'Bug'),
        ('feature', 'Feature'),
        ('improvement', 'Improvement'),
        ('research', 'Research'),
        ('review', 'Review'),
    ]
    
    # Legacy status choices for backward compatibility
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('ON_HOLD', 'On Hold'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Basic information
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    task_type = models.CharField(max_length=20, choices=TASK_TYPES, default='task')
    
    # Project and relationships
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name="tasks")
    # Legacy field name for compatibility
    project_task = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name="legacy_tasks", null=True, blank=True)
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subtasks')
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    
    # Assignment and responsibility
    assigned_to = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="assigned_tasks"
    )
    
    # Timeline and scheduling
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(db_index=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    # Status and progress - dual system for compatibility
    status = models.ForeignKey(TaskStatus, on_delete=models.PROTECT, null=True, blank=True)
    # Legacy status field for backward compatibility
    legacy_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    priority = models.IntegerField(choices=PRIORITY_LEVELS, default=3, db_index=True)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Time and effort tracking
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    # Dependencies and blocking
    dependencies = models.ManyToManyField(
        'self', 
        blank=True, 
        symmetrical=False, 
        related_name='dependents',
        help_text="Tasks that must be completed before this task can start"
    )
    blocking_reason = models.TextField(blank=True, help_text="Reason why task is blocked")
    
    # Organization and metadata
    tags = models.ManyToManyField(Tag, blank=True, related_name="tasks")
    labels = models.CharField(max_length=500, blank=True, help_text="Comma-separated labels")
    
    # Legacy file attachment field
    attachment = models.FileField(upload_to='task_attachments/', null=True, blank=True)
    
    # Quality and review
    reviewer = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="tasks_to_review"
    )
    review_notes = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        # Sync project_task with project for legacy compatibility
        if self.project and not self.project_task:
            self.project_task = self.project
        elif self.project_task and not self.project:
            self.project = self.project_task
        super().save(*args, **kwargs)
    
    @property
    def status_display(self):
        """Get status display for legacy compatibility"""
        if self.status:
            return self.status.name
        return dict(self.STATUS_CHOICES).get(self.legacy_status, self.legacy_status)
    
    def get_status_display(self):
        """Django method for status display"""
        return self.status_display
    
    def __str__(self):
        project_code = self.project.code if self.project else 'NO-CODE'
        return f"[{project_code}] {self.title}"
    
    def is_overdue(self):
        """Check if task is past its due date."""
        if self.status and self.status.is_final:
            return False
        if self.legacy_status in ['COMPLETED', 'CANCELLED']:
            return False
        return self.due_date < timezone.now().date()
    
    def is_blocked(self):
        """Check if task is blocked by dependencies."""
        if self.status and self.status.is_blocked:
            return True
        return self.dependencies.filter(
            models.Q(status__is_final=False) | models.Q(legacy_status__in=['NOT_STARTED', 'IN_PROGRESS'])
        ).exists()
    
    def can_start(self):
        """Check if task can be started (all dependencies completed)."""
        return not self.is_blocked()
    
    def get_time_utilization(self):
        """Calculate time utilization percentage."""
        if not self.estimated_hours or self.estimated_hours == 0:
            return 0
        return (self.actual_hours / self.estimated_hours) * 100
    
    def get_subtasks_progress(self):
        """Calculate progress based on subtasks completion."""
        subtasks = self.subtasks.all()
        if not subtasks:
            return self.progress_percentage
        
        total_subtasks = subtasks.count()
        completed_subtasks = subtasks.filter(
            models.Q(status__is_final=True) | models.Q(legacy_status='COMPLETED')
        ).count()
        return (completed_subtasks / total_subtasks) * 100
    
    def get_absolute_url(self):
        return reverse('common:task_detail', kwargs={'pk': self.pk})
    
    class Meta:
        permissions = [
            ("manage_tasks", "Can create, update, and delete tasks"),
            ("assign_tasks", "Can assign tasks to users"),
            ("review_tasks", "Can review and approve tasks"),
        ]
        indexes = [
            models.Index(fields=['project', 'legacy_status']),
            models.Index(fields=['assigned_to', 'due_date']),
            models.Index(fields=['priority', 'due_date']),
            models.Index(fields=['legacy_status', 'due_date']),
        ]


class TaskAssignment(models.Model):
    """
    Track task assignment history and changes.
    """
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='task_assignments_made')
    unassigned_at = models.DateTimeField(null=True, blank=True)
    is_current = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['task', 'is_current']),
        ]


### ========== TIME TRACKING SYSTEM ========== ###

class TimeEntry(BaseModel):
    """
    Detailed time tracking for tasks and projects.
    """
    
    ENTRY_TYPES = [
        ('work', 'Work'),
        ('meeting', 'Meeting'),
        ('review', 'Review'),
        ('research', 'Research'),
        ('testing', 'Testing'),
        ('documentation', 'Documentation'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_entries')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_entries')
    project = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name='time_entries')
    
    # Time tracking
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes")
    
    # Classification
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='work')
    description = models.TextField(blank=True)
    
    # Billing and approval
    is_billable = models.BooleanField(default=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_time_entries')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.task.title} ({self.duration_minutes}min)"
    
    def save(self, *args, **kwargs):
        # Auto-calculate duration if start and end times are provided
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            self.duration_minutes = int(duration.total_seconds() / 60)
        
        # Auto-assign project from task
        if self.task and not self.project:
            self.project = self.task.project
            
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['user', 'start_time']),
            models.Index(fields=['project', 'start_time']),
            models.Index(fields=['task', 'start_time']),
        ]


### ========== COLLABORATION SYSTEM ========== ###

class Comment(BaseModel):
    """
    Universal comment system for projects, tasks, and other entities.
    """
    
    COMMENT_TYPES = [
        ('comment', 'Comment'),
        ('note', 'Note'),
        ('feedback', 'Feedback'),
        ('approval', 'Approval'),
        ('rejection', 'Rejection'),
        ('question', 'Question'),
    ]
    
    # Content
    content = models.TextField()
    comment_type = models.CharField(max_length=20, choices=COMMENT_TYPES, default='comment')
    
    # Generic relationship to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Threading and replies
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # User interaction
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    mentions = models.ManyToManyField(User, blank=True, related_name='mentioned_in_comments')
    
    # Status and moderation
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_private = models.BooleanField(default=False, help_text="Only visible to project team")
    
    # Engagement
    likes = models.ManyToManyField(User, through='CommentLike', related_name='liked_comments')
    
    def __str__(self):
        return f"Comment by {self.author.get_full_name()} on {self.content_object}"
    
    def get_reply_count(self):
        """Get number of replies to this comment."""
        return self.replies.filter(is_deleted=False).count()
    
    def get_like_count(self):
        """Get number of likes on this comment."""
        return self.likes.count()
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['author', 'created_at']),
        ]


class CommentLike(models.Model):
    """Track comment likes."""
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['comment', 'user']


### ========== ATTACHMENT SYSTEM ========== ###

class Attachment(BaseModel):
    """
    Universal file attachment system with versioning and metadata.
    """
    
    FILE_TYPES = [
        ('document', 'Document'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('archive', 'Archive'),
        ('other', 'Other'),
    ]
    
    # File information
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, default='other')
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    
    # Metadata
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_files')
    
    # Version control
    version = models.CharField(max_length=20, default='1.0')
    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='newer_versions')
    
    # Access control
    is_public = models.BooleanField(default=False)
    download_count = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    def get_file_size_display(self):
        """Get human-readable file size."""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    class Meta:
        ordering = ['-created_at']


### ========== ACTIVITY AND AUDIT SYSTEM ========== ###

class ActivityLog(models.Model):
    """
    Comprehensive activity logging for audit trails and activity feeds.
    """
    
    ACTION_TYPES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('assign', 'Assigned'),
        ('unassign', 'Unassigned'),
        ('comment', 'Commented'),
        ('upload', 'Uploaded'),
        ('download', 'Downloaded'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('complete', 'Completed'),
        ('start', 'Started'),
        ('pause', 'Paused'),
        ('resume', 'Resumed'),
    ]
    
    # Actor and action
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    description = models.TextField()
    
    # Target object (generic)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Context and metadata
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Related objects (for complex activities)
    related_project = models.ForeignKey(Projects, on_delete=models.SET_NULL, null=True, blank=True)
    related_task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()} {self.action_type} {self.content_object}"
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['related_project', 'timestamp']),
            models.Index(fields=['action_type', 'timestamp']),
        ]


### ========== NOTIFICATION SYSTEM ========== ###


class Notification(BaseModel):
    """
    Comprehensive notification system with preferences and delivery tracking.
    """
    
    NOTIFICATION_TYPES = [
        ('task_assigned', 'Task Assigned'),
        ('task_due', 'Task Due'),
        ('task_completed', 'Task Completed'),
        ('project_updated', 'Project Updated'),
        ('comment_added', 'Comment Added'),
        ('mention', 'Mentioned'),
        ('event_reminder', 'Event Reminder'),
        ('approval_request', 'Approval Request'),
        ('milestone_reached', 'Milestone Reached'),
        ('deadline_approaching', 'Deadline Approaching'),
        ('system_alert', 'System Alert'),
    ]
    
    DELIVERY_METHODS = [
        ('in_app', 'In-App'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push'),
    ]
    
    # Recipients and targeting
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    
    # Content
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Target object (what triggered the notification) - NOW OPTIONAL
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)  # Changed: added null=True, blank=True
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Delivery and status
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS, default='in_app')
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_delivered = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Scheduling and expiry
    scheduled_for = models.DateTimeField(null=True, blank=True, help_text="When to send notification")
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    action_url = models.URLField(blank=True, help_text="URL to navigate to when clicked")
    extra_data = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        recipient_name = self.recipient.get_full_name() if self.recipient else "Unknown"
        return f"Notification for {recipient_name}: {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def is_expired(self):
        """Check if notification has expired."""
        return self.expires_at and timezone.now() > self.expires_at
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['scheduled_for', 'is_delivered']),
        ]




### ========== RESOURCE AND TRAINING SYSTEM ========== ###

class Resource(BaseModel):
    """
    Enhanced resource management with categorization, versioning, and access tracking.
    """
    
    RESOURCE_TYPES = [
        ('document', 'Document'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('link', 'External Link'),
        ('course', 'Training Course'),
        ('template', 'Template'),
        ('tool', 'Tool'),
        ('reference', 'Reference Material'),
    ]
    
    ACCESS_LEVELS = [
        ('public', 'Public'),
        ('internal', 'Internal Only'),
        ('team', 'Team Members'),
        ('restricted', 'Restricted'),
    ]
    
    # Basic information
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    summary = models.CharField(max_length=500, blank=True)
    
    # Classification
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    category = models.CharField(max_length=100, blank=True)
    
    # Content
    content = models.TextField(blank=True, help_text="Text content or instructions")
    file = models.FileField(upload_to="resources/%Y/%m/", blank=True, null=True)
    url = models.URLField(blank=True, help_text="External link")
    
    # Access and permissions
    access_level = models.CharField(max_length=20, choices=ACCESS_LEVELS, default='internal')
    allowed_users = models.ManyToManyField(User, blank=True, related_name='accessible_resources')
    
    # Metadata and organization
    tags = models.ManyToManyField(Tag, blank=True, related_name="resources")
    author = models.CharField(max_length=200, blank=True, help_text="Original author")
    version = models.CharField(max_length=20, default='1.0')
    
    # Usage analytics
    view_count = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.PositiveIntegerField(default=0)
    
    # Status
    is_featured = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('common:resource_detail', kwargs={'pk': self.pk})
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['resource_type', 'access_level']),
            models.Index(fields=['is_featured', 'is_archived']),
        ]


class ResourceRating(models.Model):
    """Track resource ratings and reviews."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['resource', 'user']


### ========== QUIZ AND ASSESSMENT SYSTEM ========== ###

class Quiz(BaseModel):
    """Enhanced quiz system with scoring and progress tracking."""
    
    QUIZ_TYPES = [
        ('assessment', 'Assessment'),
        ('training', 'Training'),
        ('certification', 'Certification'),
        ('survey', 'Survey'),
    ]
    
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, related_name="quiz")
    quiz_type = models.CharField(max_length=20, choices=QUIZ_TYPES, default='training')
    
    # Configuration
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=3)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70.00)
    randomize_questions = models.BooleanField(default=False)
    show_correct_answers = models.BooleanField(default=True)
    
    # Status
    is_published = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Quiz: {self.resource.title}"
    
    def get_question_count(self):
        return self.questions.count()


class Question(BaseModel):
    """Enhanced question model with different types and metadata."""
    
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('single_choice', 'Single Choice'),
        ('true_false', 'True/False'),
        ('text', 'Text Answer'),
        ('number', 'Number'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='single_choice')
    
    # Content
    text = models.TextField()
    explanation = models.TextField(blank=True, help_text="Explanation shown after answering")
    
    # Configuration
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}..."
    
    class Meta:
        ordering = ['order']


class Answer(BaseModel):
    """Enhanced answer model with scoring and feedback."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    feedback = models.TextField(blank=True, help_text="Feedback for this answer choice")
    
    def __str__(self):
        return self.text[:50]
    
    class Meta:
        ordering = ['order']


class QuizAttempt(BaseModel):
    """Track quiz attempts and scores."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    
    # Attempt details
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken_minutes = models.PositiveIntegerField(null=True, blank=True)
    
    # Scoring
    total_questions = models.PositiveIntegerField()
    correct_answers = models.PositiveIntegerField(default=0)
    total_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Status
    is_completed = models.BooleanField(default=False)
    is_passed = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.quiz.resource.title} ({self.score_percentage}%)"
    
    def calculate_score(self):
        """Calculate and update the attempt score."""
        responses = self.responses.all()
        self.total_questions = responses.count()
        self.correct_answers = responses.filter(is_correct=True).count()
        self.total_points = responses.aggregate(total=models.Sum('points_earned'))['total'] or 0
        
        if self.total_questions > 0:
            self.score_percentage = (self.correct_answers / self.total_questions) * 100
            self.is_passed = self.score_percentage >= self.quiz.passing_score
        
        self.save()
    
    class Meta:
        unique_together = ['quiz', 'user', 'created_at']  # Allow multiple attempts


class QuizResponse(models.Model):
    """Individual responses to quiz questions."""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answers = models.ManyToManyField(Answer, blank=True)
    text_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    points_earned = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    class Meta:
        unique_together = ['attempt', 'question']