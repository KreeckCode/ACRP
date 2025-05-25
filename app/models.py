from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator

User = get_user_model()

### 1. Calendar and Event Management ###

class Event(models.Model):
    """
    Represents an event or meeting in the organisation’s calendar.
    Only users with specific roles can create, update, or delete events.
    """
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_all_day = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_events")
    participants = models.ManyToManyField(User, related_name="event_participations", blank=True)
    is_mandatory = models.BooleanField(default=False)
    
    def __str__(self):
        return self.title

    def is_upcoming(self):
        """Returns True if the event is upcoming."""
        return self.start_time > timezone.now()

    class Meta:
        ordering = ['-start_time']
        permissions = [
            ("manage_events", "Can create, update, and delete events")
        ]


### 2. Announcements and Internal News ###

class Announcement(models.Model):
    """
    Represents an internal announcement, visible to all users.
    Only users with specific roles can create or edit announcements.
    """
    title = models.CharField(max_length=100)
    content = models.TextField()
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="posted_announcements")
    date_posted = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_urgent = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def has_expired(self):
        """Returns True if the announcement has expired."""
        return self.expires_at and timezone.now() > self.expires_at

    class Meta:
        ordering = ['-date_posted']
        permissions = [
            ("manage_announcements", "Can create, update, and delete announcements")
        ]


### 3. Notifications and Alerts ###
'''
class Notification(models.Model):
    """
    Represents notifications for users regarding actions like task deadlines or events.
    Notifications are generated automatically based on system triggers.
    """
    NOTIFICATION_TYPES = [
        ('EVENT_REMINDER', 'Event Reminder'),
        ('DEADLINE', 'Task Deadline'),
        ('APPROVAL_REQUEST', 'Approval Request'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    linked_event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    
    def __str__(self):
        return f"Notification for {self.user} - {self.notification_type}"

    class Meta:
        ordering = ['-created_at']
'''

### 4. Project Management Overview ###
class Tag(models.Model):
    """
    Represents a tag that can be associated with projects for categorization.
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Tags"


class Projects(models.Model):
    """
    Represents an organisational project with assigned team members and a status.
    """
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('ON_HOLD', 'On Hold')
    ]

    name = models.CharField(max_length=150)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="managed_projects")
    team_members = models.ManyToManyField(User, related_name="projects", blank=True)
    task = models.JSONField(blank=True, null=True)  # Replaced ArrayField with JSONField
    budget_allocated = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    attachment = models.FileField(upload_to='project_attachments/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="projects")
    
    def __str__(self):
        return self.name

    def is_active(self):
        """Checks if the project is currently active based on status and dates."""
        return self.status in ['IN_PROGRESS', 'ON_HOLD'] and (self.start_date <= timezone.now().date() <= (self.end_date or timezone.now().date()))

    class Meta:
        ordering = ['-start_date']
        permissions = [
            ("manage_projects", "Can create, update, and delete projects")
        ]


class Task(models.Model):
    """
    Represents an individual task within a project.
    """
    project_task = models.ForeignKey(Projects, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="tasks")
    due_date = models.DateField()
    tags = models.ManyToManyField(Tag, blank=True, related_name="tasks")
    priority = models.IntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])  # 1: High, 5: Low
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_tasks")
    updated_at = models.DateTimeField(auto_now=True)
    attachment = models.FileField(upload_to='task_attachments/', blank=True, null=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-due_date']


### 5. Training and Resources Hub ###

class Resource(models.Model):
    """
    Represents a resource available in the training hub, such as documents, videos, or knowledge articles.
    """
    RESOURCE_TYPES = [
        ('DOCUMENT', 'Document'),
        ('VIDEO', 'Video'),
        ('ARTICLE', 'Article'),
        ('QUIZ', 'Quiz')
    ]

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    file = models.FileField(upload_to='training_resources/', blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="uploaded_resources")

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class Quiz(models.Model):
    """
    Represents a quiz for training validation, associated with a specific resource.
    """
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, related_name="quiz", limit_choices_to={'resource_type': 'QUIZ'})
    questions = models.ManyToManyField('Question', related_name="quizzes")

    def __str__(self):
        return f"Quiz for {self.resource.title}"


class Question(models.Model):
    """
    Represents a question for training validation within a quiz.
    """
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text


class Answer(models.Model):
    """
    Represents an answer to a question, with a field to mark correct answers.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text

    class Meta:
        unique_together = ('question', 'text')
