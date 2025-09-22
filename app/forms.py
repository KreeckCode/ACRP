from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
import re

from tinymce.widgets import TinyMCE

from .models import (
    Event, Announcement, Projects, Task, Resource, Quiz, Question, Answer,
    Tag, Comment, TimeEntry, Milestone, ProjectMembership, TaskStatus,
    ProjectStatus, Attachment, Notification
)

User = get_user_model()

### ========== CUSTOM FORM FIELDS AND WIDGETS ========== ###

class TagField(forms.CharField):
    """
    Custom field for handling comma-separated tags with validation and auto-completion.
    Provides intelligent tag suggestions and prevents duplicate/invalid tags.
    """
    
    def __init__(self, *args, **kwargs):
        self.max_tags = kwargs.pop('max_tags', 10)
        self.min_tag_length = kwargs.pop('min_tag_length', 2)
        self.max_tag_length = kwargs.pop('max_tag_length', 50)
        super().__init__(*args, **kwargs)
    
    def to_python(self, value):
        """Convert comma-separated string to list of clean tag names."""
        if not value:
            return []
        
        # Split by comma and clean each tag
        tags = []
        for tag in value.split(','):
            clean_tag = tag.strip().lower()
            if clean_tag and len(clean_tag) >= self.min_tag_length:
                # Remove special characters except hyphens and underscores
                clean_tag = re.sub(r'[^\w\-]', '', clean_tag)
                if clean_tag and len(clean_tag) <= self.max_tag_length:
                    tags.append(clean_tag)
        
        # Remove duplicates while preserving order
        unique_tags = []
        for tag in tags:
            if tag not in unique_tags:
                unique_tags.append(tag)
        
        return unique_tags[:self.max_tags]  # Limit to max_tags
    
    def validate(self, value):
        """Validate tag list."""
        super().validate(value)
        if len(value) > self.max_tags:
            raise ValidationError(f'Maximum {self.max_tags} tags allowed.')


class UserSelectWidget(forms.Select):
    """Enhanced user selection widget with search and avatars."""
    
    def __init__(self, attrs=None, choices=(), queryset=None):
        if queryset is not None:
            choices = [(user.id, f"{user.get_full_name()} ({user.username})") 
                      for user in queryset]
        super().__init__(attrs, choices)


class DateTimePickerWidget(forms.DateTimeInput):
    """Enhanced datetime picker with timezone support."""
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {
            'type': 'datetime-local',
            'class': 'form-control datetime-picker',
            'data-toggle': 'datetimepicker'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, format=format)


class PriorityWidget(forms.Select):
    """Custom priority selection widget with visual indicators."""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control priority-select',
            'data-toggle': 'priority-picker'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'expires_at', 'is_urgent']
        widgets = {
            'content': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'expires_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
        }



### ========== ENHANCED EVENT FORMS ========== ###

class EventForm(forms.ModelForm):
    """
    Comprehensive event form with recurrence, reminders, and advanced scheduling.
    Includes intelligent conflict detection and resource booking.
    """
    
    # Custom fields for enhanced functionality
    send_notifications = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Send email notifications to all participants"
    )
    
    reminder_time = forms.ChoiceField(
        choices=[
            ('', 'No reminder'),
            ('15', '15 minutes before'),
            ('30', '30 minutes before'),
            ('60', '1 hour before'),
            ('1440', '1 day before'),
            ('10080', '1 week before'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Event
        fields = [
            'title', 'description', 'location', 'virtual_link',
            'start_time', 'end_time', 'timezone', 'is_all_day',
            'event_type', 'is_mandatory', 'is_public', 'max_participants',
            'recurrence_type', 'recurrence_interval', 'recurrence_end_date',
            'participants', 'related_project', 'related_tasks', 'tags'
        ]
        
        widgets = {
            'description': TinyMCE(attrs={'cols': 80, 'rows': 10}),
            'start_time': DateTimePickerWidget(),
            'end_time': DateTimePickerWidget(),
            'participants': forms.CheckboxSelectMultiple(attrs={
                'class': 'participant-selector'
            }),
            'related_tasks': forms.CheckboxSelectMultiple(),
            'recurrence_end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'timezone': forms.Select(attrs={'class': 'form-control timezone-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Customize participant choices based on user's projects
        if self.user:
            # Get all users from user's projects plus all active users
            project_users = User.objects.filter(
                Q(managed_projects__team_members=self.user) |
                Q(projects__manager=self.user) |
                Q(projects__team_members=self.user)
            ).distinct()
            
            self.fields['participants'].queryset = project_users.order_by(
                'first_name', 'last_name'
            )
            
            # Limit related projects to user's projects
            self.fields['related_project'].queryset = Projects.objects.filter(
                Q(manager=self.user) | Q(team_members=self.user),
                is_active=True
            ).distinct()
        
        # Dynamic task choices based on selected project (handled via JavaScript)
        self.fields['related_tasks'].queryset = Task.objects.none()
        
        # Pre-populate timezone with user's timezone if available
        if hasattr(self.user, 'profile') and hasattr(self.user.profile, 'timezone'):
            self.fields['timezone'].initial = self.user.profile.timezone
    
    def clean(self):
        """Comprehensive validation for event data."""
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        max_participants = cleaned_data.get('max_participants')
        participants = cleaned_data.get('participants')
        recurrence_type = cleaned_data.get('recurrence_type')
        recurrence_end_date = cleaned_data.get('recurrence_end_date')
        
        # Validate time range
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError("End time must be after start time.")
            
            # Check for reasonable duration (not more than 24 hours for single events)
            duration = end_time - start_time
            if duration.total_seconds() > 86400:  # 24 hours
                raise ValidationError("Event duration cannot exceed 24 hours.")
            
            # Check for conflicts with existing events for the user
            conflicting_events = Event.objects.filter(
                participants=self.user,
                start_time__lt=end_time,
                end_time__gt=start_time,
                is_active=True
            )
            
            if self.instance.pk:
                conflicting_events = conflicting_events.exclude(pk=self.instance.pk)
            
            if conflicting_events.exists():
                self.add_error('start_time', 
                    f"You have conflicting events: {', '.join([e.title for e in conflicting_events[:3]])}")
        
        # Validate participant limit
        if max_participants and participants:
            if participants.count() > max_participants:
                raise ValidationError(
                    f"Cannot select more than {max_participants} participants."
                )
        
        # Validate recurrence settings
        if recurrence_type and recurrence_type != 'none':
            if not recurrence_end_date:
                raise ValidationError(
                    "Recurrence end date is required for recurring events."
                )
            
            if recurrence_end_date and start_time:
                if recurrence_end_date <= start_time.date():
                    raise ValidationError(
                        "Recurrence end date must be after event start date."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Enhanced save method with notification and recurrence handling."""
        event = super().save(commit=False)
        
        if commit:
            event.save()
            self.save_m2m()
            
            # Handle notifications if requested
            if self.cleaned_data.get('send_notifications'):
                self._send_event_notifications(event)
            
            # Handle recurrence creation
            if event.recurrence_type != 'none':
                self._create_recurring_events(event)
        
        return event
    
    def _send_event_notifications(self, event):
        """Send notifications to all participants."""
        from .utils import send_notification
        
        for participant in event.participants.all():
            if participant != self.user:  # Don't notify the creator
                send_notification(
                    recipient=participant,
                    notification_type='event_reminder',
                    title=f'New event: {event.title}',
                    message=f'You have been invited to "{event.title}" on {event.start_time.strftime("%B %d, %Y at %I:%M %p")}',
                    content_object=event,
                    action_url=event.get_absolute_url()
                )
    
    def _create_recurring_events(self, event):
        """Create recurring event instances."""
        # Implementation for creating recurring events
        # This would create multiple event instances based on recurrence pattern
        pass


### ========== ENHANCED PROJECT FORMS ========== ###

class ProjectForm(forms.ModelForm):
    """
    Comprehensive project form with team management, budget tracking,
    and milestone planning. Includes project template support.
    """
    
    # Enhanced tag field
    tag_input = TagField(
        required=False,
        max_tags=15,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter tags separated by commas (e.g., web-dev, urgent, client-work)',
            'class': 'form-control tag-input',
            'data-toggle': 'tag-autocomplete'
        }),
        help_text="Add up to 15 tags to categorize this project"
    )
    
    # Team invitation field
    invite_members = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter email addresses to invite new team members',
            'class': 'form-control email-input'
        }),
        help_text="Comma-separated email addresses for non-registered users"
    )
    
    # Project template selection
    template = forms.ChoiceField(
        choices=[
            ('', 'Start from scratch'),
            ('web_development', 'Web Development Project'),
            ('marketing_campaign', 'Marketing Campaign'),
            ('product_launch', 'Product Launch'),
            ('research_project', 'Research Project'),
            ('event_planning', 'Event Planning'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control template-selector'})
    )
    
    # Budget breakdown
    budget_categories = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Personnel: $50000\nMaterials: $10000\nMarketing: $5000',
            'rows': 4,
            'class': 'form-control'
        }),
        help_text="Optional budget breakdown by category (one per line)"
    )
    
    class Meta:
        model = Projects
        fields = [
            'name', 'code', 'description', 'objectives',
            'start_date', 'planned_end_date', 'priority', 'status',
            'manager', 'team_members', 'client',
            'budget_allocated', 'estimated_hours',
            'is_public', 'parent_project'
        ]
        
        widgets = {
            'description': TinyMCE(attrs={'cols': 80, 'rows': 8}),
            'objectives': TinyMCE(attrs={'cols': 80, 'rows': 6}),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'planned_end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'priority': PriorityWidget(),
            'team_members': forms.CheckboxSelectMultiple(attrs={
                'class': 'team-member-selector'
            }),
            'budget_allocated': forms.NumberInput(attrs={
                'class': 'form-control currency-input',
                'step': '0.01',
                'min': '0'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Auto-generate project code if not provided
        if not self.instance.pk:
            self.fields['code'].help_text = "Leave blank to auto-generate"
        
        # Limit manager choices to users with appropriate permissions
        self.fields['manager'].queryset = User.objects.filter(
            Q(user_permissions__codename='manage_projects') |
            Q(groups__permissions__codename='manage_projects') |
            Q(is_staff=True)
        ).distinct().order_by('first_name', 'last_name')
        
        # Set current user as default manager for new projects
        if not self.instance.pk and self.user:
            self.fields['manager'].initial = self.user
        
        # Limit team members to active users
        self.fields['team_members'].queryset = User.objects.filter(
            is_active=True
        ).order_by('first_name', 'last_name')
        
        # Limit parent project to user's accessible projects
        if self.user:
            self.fields['parent_project'].queryset = Projects.objects.filter(
                Q(manager=self.user) | Q(team_members=self.user),
                is_active=True
            ).distinct().exclude(pk=self.instance.pk if self.instance.pk else None)
        
        # Pre-populate tags for existing projects
        if self.instance.pk:
            self.fields['tag_input'].initial = ', '.join(
                tag.name for tag in self.instance.tags.all()
            )
    
    def clean_code(self):
        """Validate and auto-generate project code."""
        code = self.cleaned_data.get('code')
        
        if not code:
            # Auto-generate code from project name
            name = self.cleaned_data.get('name', '')
            if name:
                # Create code from first letters of words, max 8 chars
                words = re.findall(r'\b\w+', name.upper())
                base_code = ''.join(word[0] for word in words)[:6]
                
                # Ensure uniqueness
                counter = 1
                code = base_code
                while Projects.objects.filter(code=code).exclude(
                    pk=self.instance.pk if self.instance.pk else None
                ).exists():
                    code = f"{base_code}{counter:02d}"
                    counter += 1
        else:
            # Validate provided code
            code = code.upper()
            if not re.match(r'^[A-Z0-9\-_]{2,20}$', code):
                raise ValidationError(
                    "Project code must be 2-20 characters, letters, numbers, hyphens and underscores only."
                )
            
            # Check uniqueness
            if Projects.objects.filter(code=code).exclude(
                pk=self.instance.pk if self.instance.pk else None
            ).exists():
                raise ValidationError("This project code is already in use.")
        
        return code
    
    def clean(self):
        """Comprehensive project validation."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        planned_end_date = cleaned_data.get('planned_end_date')
        budget_allocated = cleaned_data.get('budget_allocated')
        estimated_hours = cleaned_data.get('estimated_hours')
        parent_project = cleaned_data.get('parent_project')
        
        # Validate date range
        if start_date and planned_end_date:
            if start_date >= planned_end_date:
                raise ValidationError("Project end date must be after start date.")
            
            # Warn if project duration is unrealistic
            duration = (planned_end_date - start_date).days
            if duration > 365 * 3:  # 3 years
                self.add_warning("Project duration exceeds 3 years. Consider breaking it into phases.")
        
        # Validate budget
        if budget_allocated is not None and budget_allocated < 0:
            raise ValidationError("Budget cannot be negative.")
        
        # Validate estimated hours
        if estimated_hours is not None and estimated_hours < 1:
            raise ValidationError("Estimated hours must be at least 1.")
        
        # Validate parent project relationship
        if parent_project:
            if parent_project == self.instance:
                raise ValidationError("Project cannot be its own parent.")
            
            # Check for circular dependencies
            if self.instance.pk and self._has_circular_dependency(parent_project):
                raise ValidationError("This would create a circular dependency.")
        
        return cleaned_data
    
    def _has_circular_dependency(self, potential_parent):
        """Check for circular dependencies in project hierarchy."""
        current = potential_parent
        visited = {self.instance.pk}
        
        while current:
            if current.pk in visited:
                return True
            visited.add(current.pk)
            current = current.parent_project
        
        return False
    
    def save(self, commit=True):
        """Enhanced save with tag handling and template application."""
        project = super().save(commit=False)
        
        if commit:
            project.save()
            self.save_m2m()
            
            # Handle tags
            self._save_tags(project)
            
            # Apply template if selected
            template = self.cleaned_data.get('template')
            if template:
                self._apply_template(project, template)
            
            # Handle team member invitations
            self._handle_invitations(project)
        
        return project
    
    def _save_tags(self, project):
        """Save project tags from tag input."""
        project.tags.clear()
        tag_names = self.cleaned_data.get('tag_input', [])
        
        for tag_name in tag_names:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            project.tags.add(tag)
            
            # Update usage count
            if created:
                tag.usage_count = 1
            else:
                tag.usage_count += 1
            tag.save()
    
    def _apply_template(self, project, template_name):
        """Apply project template with default tasks and milestones."""
        templates = {
            'web_development': {
                'tasks': [
                    {'title': 'Requirements Gathering', 'priority': 2},
                    {'title': 'UI/UX Design', 'priority': 2},
                    {'title': 'Frontend Development', 'priority': 3},
                    {'title': 'Backend Development', 'priority': 3},
                    {'title': 'Testing & QA', 'priority': 2},
                    {'title': 'Deployment', 'priority': 1},
                ],
                'milestones': [
                    {'name': 'Design Approval', 'days_offset': 14},
                    {'name': 'Development Complete', 'days_offset': 60},
                    {'name': 'Go Live', 'days_offset': 90},
                ]
            },
            # Add more templates as needed
        }
        
        template_data = templates.get(template_name)
        if not template_data:
            return
        
        # Create default tasks
        for task_data in template_data.get('tasks', []):
            Task.objects.create(
                project=project,
                title=task_data['title'],
                priority=task_data['priority'],
                due_date=project.planned_end_date,
                created_by=self.user
            )
        
        # Create default milestones
        for milestone_data in template_data.get('milestones', []):
            planned_date = project.start_date + timedelta(days=milestone_data['days_offset'])
            Milestone.objects.create(
                project=project,
                name=milestone_data['name'],
                planned_date=planned_date,
                created_by=self.user
            )
    
    def _handle_invitations(self, project):
        """Send invitations to new team members."""
        invite_emails = self.cleaned_data.get('invite_members', '')
        if not invite_emails:
            return
        
        emails = [email.strip() for email in invite_emails.split(',') if email.strip()]
        
        for email in emails:
            # Check if user already exists
            try:
                user = User.objects.get(email=email)
                project.team_members.add(user)
            except User.DoesNotExist:
                # Send invitation email (implement based on your requirements)
                pass


### ========== ENHANCED TASK FORMS ========== ###

class TaskForm(forms.ModelForm):
    """
    Comprehensive task form with dependency management, time estimation,
    and intelligent assignment suggestions.
    """
    
    # Enhanced tag field
    tag_input = TagField(
        required=False,
        max_tags=10,
        widget=forms.TextInput(attrs={
            'placeholder': 'bug, frontend, urgent, review-needed',
            'class': 'form-control tag-input',
            'data-toggle': 'tag-autocomplete'
        })
    )
    
    # Dependency selection with search
    dependency_search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search for dependent tasks...',
            'class': 'form-control dependency-search',
            'data-toggle': 'task-search'
        }),
        help_text="Tasks that must be completed before this task can start"
    )
    
    # Time estimation breakdown
    estimation_breakdown = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Research: 2 hours\nDevelopment: 8 hours\nTesting: 2 hours',
            'rows': 3,
            'class': 'form-control'
        }),
        help_text="Optional breakdown of time estimates"
    )
    
    # Checklist for subtasks
    checklist = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': '- Set up development environment\n- Create database schema\n- Implement API endpoints',
            'rows': 4,
            'class': 'form-control'
        }),
        help_text="Simple checklist of subtasks (one per line, start with -)"
    )
    
    class Meta:
        model = Task
        fields = [
            'title', 'description', 'task_type', 'project',
            'assigned_to', 'reviewer', 'milestone',
            'start_date', 'due_date', 'priority', 'status',
            'estimated_hours', 'dependencies', 'labels'
        ]
        
        widgets = {
            'description': TinyMCE(attrs={'cols': 80, 'rows': 6}),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'priority': PriorityWidget(),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '0.5',
                'max': '999'
            }),
            'dependencies': forms.CheckboxSelectMultiple(),
            'labels': forms.TextInput(attrs={
                'placeholder': 'frontend, api, critical',
                'class': 'form-control'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        
        # Set project if provided
        if self.project:
            self.fields['project'].initial = self.project
            self.fields['project'].widget = forms.HiddenInput()
            
            # Limit assignees to project team members
            team_members = self.project.team_members.all()
            if self.project.manager:
                team_members = team_members | User.objects.filter(id=self.project.manager.id)
            
            self.fields['assigned_to'].queryset = team_members.distinct().order_by(
                'first_name', 'last_name'
            )
            
            # Limit reviewers to project team leads and manager
            reviewers = team_members.filter(
                project_memberships__project=self.project,
                project_memberships__role__in=['lead', 'coordinator']
            )
            if self.project.manager:
                reviewers = reviewers | User.objects.filter(id=self.project.manager.id)
            
            self.fields['reviewer'].queryset = reviewers.distinct().order_by(
                'first_name', 'last_name'
            )
            
            # Limit milestones to project milestones
            self.fields['milestone'].queryset = self.project.milestones.filter(
                is_active=True
            ).order_by('planned_date')
            
            # Limit dependencies to project tasks (excluding self)
            dependencies_qs = self.project.tasks.filter(is_active=True)
            if self.instance.pk:
                dependencies_qs = dependencies_qs.exclude(pk=self.instance.pk)
            self.fields['dependencies'].queryset = dependencies_qs.order_by('title')
        
        # Pre-populate tags for existing tasks
        if self.instance.pk:
            self.fields['tag_input'].initial = ', '.join(
                tag.name for tag in self.instance.tags.all()
            )
        
        # Auto-assign based on workload if no assignee set
        if not self.instance.pk and self.project and not self.fields['assigned_to'].initial:
            suggested_assignee = self._suggest_assignee()
            if suggested_assignee:
                self.fields['assigned_to'].initial = suggested_assignee
    
    def _suggest_assignee(self):
        """Suggest the team member with the lowest current workload."""
        if not self.project:
            return None
        
        team_members = self.project.team_members.all()
        if not team_members.exists():
            return self.project.manager
        
        # Calculate workload for each team member
        workloads = []
        for member in team_members:
            active_tasks = member.assigned_tasks.filter(
                project=self.project,
                status__is_final=False,
                is_active=True
            ).count()
            workloads.append((member, active_tasks))
        
        # Return member with lowest workload
        if workloads:
            workloads.sort(key=lambda x: x[1])
            return workloads[0][0]
        
        return self.project.manager
    
    def clean(self):
        """Comprehensive task validation."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        due_date = cleaned_data.get('due_date')
        project = cleaned_data.get('project')
        assigned_to = cleaned_data.get('assigned_to')
        dependencies = cleaned_data.get('dependencies', [])
        estimated_hours = cleaned_data.get('estimated_hours')
        
        # Validate date range
        if start_date and due_date:
            if start_date > due_date:
                raise ValidationError("Due date must be after start date.")
        
        # Validate project dates
        if due_date and project:
            if due_date > project.planned_end_date:
                self.add_warning(
                    f"Task due date is after project end date ({project.planned_end_date})"
                )
        
        # Validate assignee is part of project team
        if assigned_to and project:
            if (assigned_to != project.manager and 
                assigned_to not in project.team_members.all()):
                raise ValidationError(
                    f"{assigned_to.get_full_name()} is not a member of this project."
                )
        
        # Validate dependencies
        if dependencies:
            for dep_task in dependencies:
                if dep_task.project != project:
                    raise ValidationError(
                        f"Dependency '{dep_task.title}' is not in the same project."
                    )
                
                if dep_task == self.instance:
                    raise ValidationError("Task cannot depend on itself.")
                
                # Check for circular dependencies
                if self.instance.pk and self._has_circular_dependency(dep_task):
                    raise ValidationError(
                        f"Adding '{dep_task.title}' as dependency would create a circular dependency."
                    )
        
        # Validate estimated hours
        if estimated_hours is not None:
            if estimated_hours <= 0:
                raise ValidationError("Estimated hours must be greater than 0.")
            elif estimated_hours > 999:
                raise ValidationError("Estimated hours cannot exceed 999.")
        
        return cleaned_data
    
    def _has_circular_dependency(self, potential_dependency):
        """Check for circular dependencies."""
        visited = {self.instance.pk}
        queue = [potential_dependency]
        
        while queue:
            current = queue.pop(0)
            if current.pk in visited:
                return True
            
            visited.add(current.pk)
            queue.extend(current.dependencies.all())
        
        return False
    
    def save(self, commit=True):
        """Enhanced save with automatic status updates and notifications."""
        task = super().save(commit=False)
        
        # Auto-set creator if not set
        if not task.created_by and self.user:
            task.created_by = self.user
        
        # Fix: Handle project assignment from form data
        if not task.project and hasattr(self, 'cleaned_data'):
            project_id = self.cleaned_data.get('project_id') or self.data.get('project_id')
            if project_id:
                try:
                    task.project = Projects.objects.get(id=project_id)
                except Projects.DoesNotExist:
                    pass
        
        # Auto-set initial status if not set
        if not task.status:
            initial_status = TaskStatus.objects.filter(
                is_initial=True, is_active=True
            ).first()
            if initial_status:
                task.status = initial_status
        
        if commit:
            task.save()
            self.save_m2m()
            
            # Handle tags
            self._save_tags(task)
            
            # Create checklist items as subtasks
            self._create_checklist_items(task)
            
            # Send notifications
            self._send_notifications(task)
        
        return task
    
    def _save_tags(self, task):
        """Save task tags from tag input."""
        task.tags.clear()
        tag_names = self.cleaned_data.get('tag_input', [])
        
        for tag_name in tag_names:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            task.tags.add(tag)
            
            if created:
                tag.usage_count = 1
            else:
                tag.usage_count += 1
            tag.save()
    
    def _create_checklist_items(self, task):
        """Create subtasks from checklist input."""
        checklist = self.cleaned_data.get('checklist', '')
        if not checklist:
            return
        
        lines = checklist.strip().split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('-'):
                subtask_title = line[1:].strip()
                if subtask_title:
                    Task.objects.create(
                        title=subtask_title,
                        project=task.project,
                        parent_task=task,
                        assigned_to=task.assigned_to,
                        due_date=task.due_date,
                        priority=task.priority,
                        created_by=self.user,
                        estimated_hours=0.5  # Default for checklist items
                    )
    
    def _send_notifications(self, task):
        """Send notifications for task assignment and mentions."""
        from .utils import send_notification
        
        # Notify assignee if different from creator
        if task.assigned_to and task.assigned_to != self.user:
            send_notification(
                recipient=task.assigned_to,
                notification_type='task_assigned',
                title=f'Task assigned: {task.title}',
                message=f'{self.user.get_full_name()} assigned you a task in {task.project.name}',
                content_object=task,
                action_url=task.get_absolute_url()
            )
        
        # Notify reviewer if set
        if task.reviewer and task.reviewer != self.user and task.reviewer != task.assigned_to:
            send_notification(
                recipient=task.reviewer,
                notification_type='task_assigned',
                title=f'Task review requested: {task.title}',
                message=f'{self.user.get_full_name()} requested your review for a task in {task.project.name}',
                content_object=task,
                action_url=task.get_absolute_url()
            )


### ========== TIME TRACKING FORMS ========== ###

class TimeEntryForm(forms.ModelForm):
    """
    Comprehensive time entry form with intelligent task detection,
    automatic duration calculation, and project validation.
    """
    
    # Quick time buttons (handled via JavaScript)
    quick_duration = forms.ChoiceField(
        choices=[
            ('', 'Custom'),
            ('15', '15 minutes'),
            ('30', '30 minutes'),
            ('60', '1 hour'),
            ('120', '2 hours'),
            ('240', '4 hours'),
            ('480', '8 hours'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control quick-duration'})
    )
    
    class Meta:
        model = TimeEntry
        fields = [
            'task', 'project', 'start_time', 'end_time', 'duration_minutes',
            'entry_type', 'description', 'is_billable', 'hourly_rate'
        ]
        
        widgets = {
            'start_time': DateTimePickerWidget(),
            'end_time': DateTimePickerWidget(),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Describe what you worked on...'
            }),
            'hourly_rate': forms.NumberInput(attrs={
                'class': 'form-control currency-input',
                'step': '0.01',
                'min': '0'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Limit tasks to user's assigned tasks
            self.fields['task'].queryset = Task.objects.filter(
                Q(assigned_to=self.user) | Q(project__team_members=self.user),
                is_active=True,
                status__is_final=False
            ).select_related('project').order_by('-updated_at')
            
            # Limit projects to user's accessible projects
            self.fields['project'].queryset = Projects.objects.filter(
                Q(manager=self.user) | Q(team_members=self.user),
                is_active=True
            ).order_by('name')
        
        # Set default values for new entries
        if not self.instance.pk:
            now = timezone.now()
            self.fields['start_time'].initial = now.replace(minute=0, second=0, microsecond=0)
            self.fields['is_billable'].initial = True
    
    def clean(self):
        """Validate time entry data."""
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        duration_minutes = cleaned_data.get('duration_minutes')
        task = cleaned_data.get('task')
        project = cleaned_data.get('project')
        
        # Validate time range or duration
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError("End time must be after start time.")
            
            # Calculate duration and update field
            calculated_duration = int((end_time - start_time).total_seconds() / 60)
            cleaned_data['duration_minutes'] = calculated_duration
            
        elif start_time and duration_minutes:
            # Calculate end time
            cleaned_data['end_time'] = start_time + timedelta(minutes=duration_minutes)
            
        elif not duration_minutes:
            raise ValidationError("Either provide start/end times or duration.")
        
        # Validate maximum duration (24 hours)
        if duration_minutes and duration_minutes > 1440:  # 24 hours
            raise ValidationError("Time entry cannot exceed 24 hours.")
        
        # Validate task belongs to project
        if task and project:
            if task.project != project:
                raise ValidationError("Selected task does not belong to the selected project.")
        elif task and not project:
            # Auto-assign project from task
            cleaned_data['project'] = task.project
        elif project and not task:
            # This is okay - working on project in general
            pass
        else:
            raise ValidationError("Either task or project must be selected.")
        
        # Check for overlapping time entries
        if start_time and end_time and self.user:
            overlapping = TimeEntry.objects.filter(
                user=self.user,
                start_time__lt=end_time,
                end_time__gt=start_time,
                is_active=True
            )
            
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            
            if overlapping.exists():
                raise ValidationError(
                    f"This time entry overlaps with existing entry: {overlapping.first()}"
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Enhanced save with automatic project assignment."""
        time_entry = super().save(commit=False)
        
        if self.user:
            time_entry.user = self.user
        
        # Auto-assign project from task if not set
        if time_entry.task and not time_entry.project:
            time_entry.project = time_entry.task.project
        
        if commit:
            time_entry.save()
            
            # Update task actual hours
            if time_entry.task:
                self._update_task_hours(time_entry.task)
        
        return time_entry
    
    def _update_task_hours(self, task):
        """Update task's actual hours from all time entries."""
        total_minutes = TimeEntry.objects.filter(
            task=task,
            is_active=True
        ).aggregate(total=models.Sum('duration_minutes'))['total'] or 0
        
        task.actual_hours = round(total_minutes / 60, 2)
        task.save(update_fields=['actual_hours'])


### ========== COMMENT FORMS ========== ###

class CommentForm(forms.ModelForm):
    """
    Enhanced comment form with mention support, formatting options,
    and attachment handling.
    """
    
    class Meta:
        model = Comment
        fields = ['content', 'comment_type', 'is_private']
        
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control comment-editor',
                'placeholder': 'Add a comment... Use @username to mention someone',
                'data-toggle': 'mention-autocomplete'
            }),
            'comment_type': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.content_object = kwargs.pop('content_object', None)
        super().__init__(*args, **kwargs)
        
        # Customize comment types based on user permissions
        if self.user and not self.user.has_perm('app.approve'):
            # Remove approval/rejection types for regular users
            choices = [choice for choice in Comment.COMMENT_TYPES 
                      if choice[0] not in ['approval', 'rejection']]
            self.fields['comment_type'].choices = choices
    
    def clean_content(self):
        """Validate comment content and extract mentions."""
        content = self.cleaned_data.get('content', '').strip()
        
        if not content:
            raise ValidationError("Comment content cannot be empty.")
        
        if len(content) > 5000:
            raise ValidationError("Comment is too long (maximum 5000 characters).")
        
        # Extract and validate mentions
        mentions = re.findall(r'@(\w+)', content)
        invalid_mentions = []
        
        for username in mentions:
            if not User.objects.filter(username=username, is_active=True).exists():
                invalid_mentions.append(username)
        
        if invalid_mentions:
            raise ValidationError(
                f"Invalid mentions: @{', @'.join(invalid_mentions)}"
            )
        
        return content


### ========== MILESTONE FORMS ========== ###

class MilestoneForm(forms.ModelForm):
    """
    Comprehensive milestone form with dependency tracking and progress monitoring.
    """
    
    class Meta:
        model = Milestone
        fields = [
            'name', 'description', 'milestone_type', 'planned_date',
            'dependencies', 'tags'
        ]
        
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control'
            }),
            'planned_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'dependencies': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        
        if self.project:
            # Limit dependencies to project milestones
            dependencies_qs = self.project.milestones.filter(is_active=True)
            if self.instance.pk:
                dependencies_qs = dependencies_qs.exclude(pk=self.instance.pk)
            self.fields['dependencies'].queryset = dependencies_qs.order_by('planned_date')
    
    def clean_planned_date(self):
        """Validate milestone date against project timeline."""
        planned_date = self.cleaned_data.get('planned_date')
        
        if planned_date and self.project:
            if planned_date < self.project.start_date:
                raise ValidationError(
                    f"Milestone date cannot be before project start date ({self.project.start_date})"
                )
            
            if planned_date > self.project.planned_end_date:
                raise ValidationError(
                    f"Milestone date cannot be after project end date ({self.project.planned_end_date})"
                )
        
        return planned_date


### ========== UTILITY FUNCTIONS ========== ###

def add_form_error(form, field, message):
    """Helper function to add errors to forms programmatically."""
    if hasattr(form, '_errors'):
        if form._errors is None:
            form._errors = {}
        if field not in form._errors:
            form._errors[field] = form.error_class()
        form._errors[field].append(message)


def add_form_warning(form, field, message):
    """Helper function to add warnings to forms."""
    if not hasattr(form, '_warnings'):
        form._warnings = {}
    if field not in form._warnings:
        form._warnings[field] = []
    form._warnings[field].append(message)

# Monkey patch the warning functionality to ModelForm
forms.ModelForm.add_warning = lambda self, field, message: add_form_warning(self, field, message)

