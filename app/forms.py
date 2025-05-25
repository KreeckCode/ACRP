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
    class Meta:
        model = Projects
        fields = ['name', 'description', 'start_date', 'end_date', 'status', 'manager', 'team_members', 'budget_allocated', 'tags', 'attachments']
        widgets = {
            'team_members': forms.CheckboxSelectMultiple(),
            'attachments': forms.ClearableFileInput(attrs={'multiple': True}),
            'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'tags': TagField(widget=forms.TextInput(attrs={'placeholder': 'Enter tags separated by commas'})),
        }

    def save(self, commit=True):
        instance = super().save(commit)
        tags = self.cleaned_data.get('tag_input')
        instance.tags.clear()
        for name in tags:
            tag, _ = Tag.objects.get_or_create(name=name)
            instance.tags.add(tag)
        return instance
    


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['project_task', 'title', 'description', 'assigned_to', 'due_date', 'completed', 'priority', 'tags', 'attachment']
        widgets = {
            'attachment': forms.ClearableFileInput(attrs={'multiple': True}),
            'tags': TagField(widget=forms.TextInput(attrs={'placeholder': 'Enter tags separated by commas'})),
            'assigned_to': forms.CheckboxSelectMultiple(),
            'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'priority': forms.Select(choices=[(1, 'High'), (2, 'Medium'), (3, 'Low')], attrs={'class': 'form-control'}),
        }

        def save(self, commit=True):
            instance = super().save(commit)
            tags = self.cleaned_data.get('tag_input')
            instance.tags.clear()
            for name in tags:
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
