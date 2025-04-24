from django import forms
from .models import Event, Announcement, Projects, Task, Resource, Quiz, Question

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'location', 'start_time', 'end_time', 'is_all_day', 'is_mandatory', 'participants']

        widgets = {
            'start_time': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'end_time': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
        }

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'expires_at', 'is_urgent']
        widgets = {
            'expires_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Projects
        fields = ['name', 'description', 'start_date', 'end_date', 'status', 'manager', 'team_members', 'budget_allocated']

        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['project_task', 'title', 'description', 'assigned_to', 'due_date', 'completed']

        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['title', 'description', 'resource_type', 'file', 'url']

class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ['resource']
