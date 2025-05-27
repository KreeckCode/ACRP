from django import forms
from .models import Event, Announcement, Projects, Task, Resource, Quiz, Question, Tag
from tinymce.widgets import TinyMCE

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'location', 'start_time', 'end_time', 'is_all_day', 'is_mandatory', 'participants']

        widgets = {
            'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
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
            'content': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'expires_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
        }



class TagField(forms.CharField):
    def to_python(self, value):
        return [v.strip() for v in value.split(',') if v.strip()]

class ProjectForm(forms.ModelForm):
    tag_input = TagField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter tags separated by commas',
            'class': 'form-control'
        }),
        help_text="Comma-separate your tags"
    )

    class Meta:
        model = Projects
        fields = [
            'name', 'description', 'start_date', 'end_date',
            'status', 'manager', 'team_members', 'budget_allocated',
            'attachment'
        ]
        widgets = {
            'team_members': forms.CheckboxSelectMultiple(),
            'description': TinyMCE(attrs={'cols': 80, 'rows': 10}),
            'start_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'end_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['tag_input'].initial = ', '.join(
                t.name for t in self.instance.tags.all()
            )

    def save(self, commit=True):
        instance = super().save(commit)
        # 3) Sync your comma-list back to the M2M
        instance.tags.clear()
        for name in self.cleaned_data.get('tag_input', []):
            tag, _ = Tag.objects.get_or_create(name=name)
            instance.tags.add(tag)
        return instance

from django.forms.widgets import HiddenInput, TextInput, Select, DateInput, CheckboxInput, ClearableFileInput


class TaskForm(forms.ModelForm):
    # user-facing comma-tag entry
    tag_input = TagField(
        required=False,
        widget=TextInput(attrs={
            'placeholder': 'Enter tags separated by commas',
            'class': 'form-control'
        }),
        help_text="Comma-separate tags"
    )

    class Meta:
        model = Task
        fields = [
            'project_task', 'title', 'description', 'assigned_to',
            'due_date', 'priority', 'attachment'
        ]
        widgets = {
            # we set project_task hidden since we'll assign it via the view/modal context
            'project_task': HiddenInput(),

            'title': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Task title'
            }),

            'description': TinyMCE(attrs={
                'cols': 80,
                'rows': 3
            }),

            'assigned_to': Select(attrs={'class': 'form-control'}),

            'due_date': DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),


            'priority': Select(choices=[
                (1, 'High'),
                (2, 'Medium'),
                (3, 'Low')
            ], attrs={'class': 'form-control'}),

            'attachment': ClearableFileInput(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing, pre-fill comma tags
        if self.instance.pk:
            self.fields['tag_input'].initial = ', '.join(
                t.name for t in self.instance.tags.all()
            )

    def save(self, commit=True):
        # Save the core model
        instance = super().save(commit=commit)
        # Sync your comma-tag input with the M2M
        instance.tags.clear()
        for name in self.cleaned_data.get('tag_input', []):
            tag, _ = Tag.objects.get_or_create(name=name)
            instance.tags.add(tag)
        return instance

class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['title', 'description', 'resource_type', 'file', 'url']

class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ['resource']
