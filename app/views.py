from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from .forms import (
    EventForm, AnnouncementForm, ProjectForm, TaskForm, ResourceForm,
    QuizForm
)
from .models import (
    Event, Announcement, Projects, Task, Resource,
    Quiz, Question
)
from django.db.models import Count, Sum
from finance.models import BudgetRequest, Expenditure, Invoice
from hr.models import EmployeeProfile, LeaveRequest, HRDocumentStorage
from database.models import Database, Entry
from accounts.models import Department, User

@login_required
def dashboard(request):
    user = request.user

    # 1) Everyone sees these three things:
    context = {
        'announcements': Announcement.objects.filter(is_urgent=True)[:5],
        'events':        Event.objects.filter(is_mandatory=True,
                                              start_time__gte=user.date_joined)[:5],
        'projects':      Projects.objects.filter(manager=user)
                                          .order_by('-start_date')[:5],
    }

    # 2) Figure out what role (if any) they actually have
    role = getattr(user, 'role', None)
    title = getattr(role, 'title', None)

    # 3) Only add the extra bits for that one role
    if title == "HR":
        context.update({
            'pending_leave_requests': LeaveRequest.objects.filter(status='PENDING').count(),
            'employee_count':         EmployeeProfile.objects.count(),
            'hr_documents':           HRDocumentStorage.objects.count(),
        })
    elif title == "Finance":
        context.update({
            'pending_budget_requests':  BudgetRequest.objects.filter(status='PENDING').count(),
            'total_expenditure':        Expenditure.objects.aggregate(total=Sum('amount_spent'))['total'] or 0,
            'unpaid_invoices':          Invoice.objects.filter(status='DRAFT').count(),
        })
    elif title == "Database Manager":
        context.update({
            'databases': Database.objects.filter(owner=user).count(),
            'entries':   Entry.objects.filter(database__owner=user).count(),
        })
    elif title == "Accounts":
        context.update({
            'user_count':       User.objects.count(),
            'department_count': Department.objects.count(),
        })
    # else: we do nothing extra

    return render(request, 'app/dashboard.html', context)


"""
@login_required
def dashboard(request):
    user = request.user
    context = {}

    context['announcements'] = Announcement.objects.filter(is_urgent=True)[:5]
    context['events'] = Event.objects.filter(is_mandatory=True, start_time__gte=user.date_joined)[:5]
    context['projects'] = Projects.objects.filter(manager=user).order_by('-start_date')[:5]

    if user.role.title == "HR":
        context['pending_leave_requests'] = LeaveRequest.objects.filter(status='PENDING').count()
        context['employee_count'] = EmployeeProfile.objects.count()
        context['hr_documents'] = HRDocumentStorage.objects.count()
    
    else:
        pass

    if user.role.title == "Finance":
        context['pending_budget_requests'] = BudgetRequest.objects.filter(status='PENDING').count()
        context['total_expenditure'] = Expenditure.objects.aggregate(Sum('amount_spent'))['amount_spent__sum']
        context['unpaid_invoices'] = Invoice.objects.filter(status='DRAFT').count()

    if user.role.title == "Database Manager":
        context['databases'] = Database.objects.filter(owner=user).count()
        context['entries'] = Entry.objects.filter(database__owner=user).count()

    if user.role.title == "Accounts":
        context['user_count'] = User.objects.count()
        context['department_count'] = Department.objects.count()

    return render(request, 'app/dashboard.html', context)

"""
### ========== EVENTS ========== ###

@login_required
def event_list(request):
    events = Event.objects.all()
    return render(request, 'app/event_list.html', {'events': events})

@login_required
@permission_required('apps.manage_events', raise_exception=True)
def create_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            form.save_m2m()  # for participants
            messages.success(request, 'Event created successfully.')
            return redirect('event_list')
    else:
        form = EventForm()
    return render(request, 'app/event_form.html', {'form': form})

@login_required
def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    return render(request, 'app/event_detail.html', {'event': event})

@login_required
@permission_required('apps.manage_events', raise_exception=True)
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully.')
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm(instance=event)
    return render(request, 'app/event_form.html', {'form': form, 'event': event})

@login_required
@permission_required('apps.manage_events', raise_exception=True)
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        event.delete()
        messages.success(request, 'Event deleted successfully.')
        return redirect('event_list')
    return render(request, 'app/confirm_delete.html', {
        'object': event, 'type': 'Event',
        'cancel_url': 'event_detail', 'cancel_id': event.id
    })


### ========== ANNOUNCEMENTS ========== ###

@login_required
def announcement_list(request):
    announcements = Announcement.objects.all()
    return render(request, 'app/announcement_list.html', {'announcements': announcements})

@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def create_announcement(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.posted_by = request.user
            ann.save()
            messages.success(request, 'Announcement posted successfully.')
            return redirect('announcement_list')
    else:
        form = AnnouncementForm()
    return render(request, 'app/announcement_form.html', {'form': form})

@login_required
def announcement_detail(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    return render(request, 'app/announcement_detail.html', {'announcement': announcement})

@login_required
@permission_required('apps.manage_announcements', raise_exception=True)
def edit_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated successfully.')
            return redirect('announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, 'app/announcement_form.html', {'form': form})

@login_required
@permission_required('app.manage_announcements', raise_exception=True)
def delete_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    if request.method == 'POST':
        announcement.delete()
        messages.success(request, 'Announcement deleted successfully.')
        return redirect('announcement_list')
    return render(request, 'app/confirm_delete.html', {
        'object': announcement, 'type': 'Announcement',
        'cancel_url': 'announcement_detail', 'cancel_id': announcement.id
    })


### ========== PROJECTS ========== ###

@login_required
def project_list(request):
    projects = Projects.objects.all()
    return render(request, 'app/project_list.html', {'projects': projects})

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project created successfully.')
            return redirect('project_list')
    else:
        form = ProjectForm()
    return render(request, 'app/project_form.html', {'form': form})

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    return render(request, 'app/project_detail.html', {'project': project})

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def edit_project(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully.')
            return redirect('project_detail', project_id=project.id)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'app/project_form.html', {'form': form})

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def delete_project(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    if request.method == 'POST':
        project.delete()
        messages.success(request, 'Project deleted successfully.')
        return redirect('project_list')
    return render(request, 'app/confirm_delete.html', {
        'object': project, 'type': 'Project',
        'cancel_url': 'project_detail', 'cancel_id': project.id
    })


### ========== TASKS ========== ###

@login_required
def task_list(request):
    tasks = Task.objects.select_related('project_task').all()
    return render(request, 'app/task_list.html', {'tasks': tasks})

@login_required
def create_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task created successfully.')
            return redirect('task_list')
    else:
        form = TaskForm()
    return render(request, 'app/task_form.html', {'form': form})

@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    return render(request, 'app/task_detail.html', {'task': task})

@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task updated successfully.')
            return redirect('task_detail', task_id=task.id)
    else:
        form = TaskForm(instance=task)
    return render(request, 'app/task_form.html', {'form': form})

@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        task.delete()
        messages.success(request, 'Task deleted successfully.')
        return redirect('task_list')
    return render(request, 'app/confirm_delete.html', {
        'object': task, 'type': 'Task',
        'cancel_url': 'task_detail', 'cancel_id': task.id
    })


### ========== RESOURCES ========== ###

@login_required
def resource_list(request):
    resources = Resource.objects.all()
    return render(request, 'app/resource_list.html', {'resources': resources})

@login_required
def create_resource(request):
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            res = form.save(commit=False)
            res.created_by = request.user
            res.save()
            messages.success(request, 'Resource created successfully.')
            return redirect('resource_list')
    else:
        form = ResourceForm()
    return render(request, 'app/resource_form.html', {'form': form})

@login_required
def resource_detail(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    return render(request, 'app/resource_detail.html', {'resource': resource})

@login_required
def edit_resource(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resource updated successfully.')
            return redirect('resource_detail', resource_id=resource.id)
    else:
        form = ResourceForm(instance=resource)
    return render(request, 'app/resource_form.html', {'form': form})

@login_required
def delete_resource(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if request.method == 'POST':
        resource.delete()
        messages.success(request, 'Resource deleted successfully.')
        return redirect('resource_list')
    return render(request, 'app/confirm_delete.html', {
        'object': resource, 'type': 'Resource',
        'cancel_url': 'resource_detail', 'cancel_id': resource.id
    })
