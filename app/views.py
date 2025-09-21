import json
from django.http import HttpResponseForbidden, JsonResponse
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
from django.db.models import Count, Sum, Q
from accounts.models import Department, User
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods

from django.utils import timezone
from datetime import timedelta

@login_required
def kanban_board(request):
    """
    A simple Kanban board view that shows tasks grouped by their status.
    """
    projects = Projects.objects.prefetch_related('tasks').all()
    tasks = Task.objects.select_related('project_task').all()
    task_statuses = {
        'To Do': tasks.filter(status='TODO'),
        'In Progress': tasks.filter(status='IN_PROGRESS'),
        'Done': tasks.filter(status='DONE'),
        'Blocked': tasks.filter(status='BLOCKED'),
    }
    return render(request, 'app/kanban_board.html', {
        'projects': projects,
        'task_statuses': task_statuses,
    })



@login_required
def dashboard(request):
    """
    Unified ACRP Dashboard - Central hub for all system modules
    
    Provides strategic overview and quick access to key functions across:
    - Enrollments (applications, members)
    - Digital Cards (verification, management) 
    - CPD (activities, records, certificates)
    - Projects & Tasks
    - System Administration
    """
    user = request.user
    
    # ============================================================================
    # SYSTEM-WIDE STATISTICS
    # ============================================================================
    
    stats = {}
    
    # Enrollment Statistics
    try:
        from enrollments.models import AssociatedApplication, DesignatedApplication, StudentApplication
        
        # Get all applications across types
        all_applications = []
        for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
            all_applications.extend(model.objects.all())
        
        stats['total_applications'] = len(all_applications)
        stats['pending_applications'] = len([app for app in all_applications if app.status in ['submitted', 'under_review']])
        stats['approved_applications'] = len([app for app in all_applications if app.status == 'approved'])
        
    except ImportError:
        stats['total_applications'] = 0
        stats['pending_applications'] = 0
        stats['approved_applications'] = 0
    
    # Digital Card Statistics
    try:
        from affiliationcard.models import AffiliationCard
        
        stats['total_cards'] = AffiliationCard.objects.count()
        stats['active_cards'] = AffiliationCard.objects.filter(status='active').count()
        stats['expiring_cards'] = AffiliationCard.objects.filter(
            date_expires__lte=timezone.now().date() + timedelta(days=30),
            status='active'
        ).count()
        
    except ImportError:
        stats['total_cards'] = 0
        stats['active_cards'] = 0
        stats['expiring_cards'] = 0
    
    # CPD Statistics
    try:
        from cpd.models import CPDRecord, CPDApproval
        
        current_year = timezone.now().year
        
        # Get completed CPD records for current year with approved status
        approved_records = CPDRecord.objects.filter(
            user=user,
            completion_date__year=current_year,
            status='COMPLETED'
        ).filter(
            approval__status='APPROVED'
        )
        
        # Calculate total hours (use hours_awarded if available, otherwise hours_claimed)
        total_hours = 0
        for record in approved_records:
            total_hours += float(record.hours_awarded or record.hours_claimed or 0)
        
        stats['cpd_hours'] = total_hours
        
    except (ImportError, AttributeError):
        stats['cpd_hours'] = 0
    
    # Active Members (approximation based on active cards or approved applications)
    stats['active_members'] = stats['active_cards'] or stats['approved_applications']
    stats['new_members'] = 0  # You can calculate this based on recent approvals
    
    # ============================================================================
    # CORE CONTENT (Existing functionality)
    # ============================================================================
    
    # Urgent announcements
    announcements = Announcement.objects.filter(is_urgent=True).order_by('-date_posted')[:5]
    
    # Mandatory events
    events = Event.objects.filter(
        is_mandatory=True,
        start_time__gte=timezone.now()
    ).order_by('start_time')[:5]
    
    # User's projects
    projects = Projects.objects.filter(
        manager=user
    ).order_by('-start_date')[:5]
    
    # ============================================================================
    # ITEMS REQUIRING ATTENTION
    # ============================================================================
    
    pending_items = []
    
    # Add role-based pending items
    if user.is_staff or hasattr(user, 'role'):
        # Applications needing review
        try:
            pending_apps = []
            for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                pending_apps.extend(
                    model.objects.filter(status='submitted').values(
                        'id', 'application_number', 'full_names', 'created_at'
                    )[:3]
                )
            
            for app in pending_apps:
                pending_items.append({
                    'type': 'application',
                    'title': f"Review Application {app['application_number']}",
                    'description': f"Application from {app['full_names']} needs review",
                    'created': app['created_at'],
                    'url': f"/enrollments/applications/",  # Generic link
                })
        except:
            pass
        
        # Cards needing attention
        try:
            expiring_cards = AffiliationCard.objects.filter(
                date_expires__lte=timezone.now().date() + timedelta(days=30),
                status='active'
            )[:3]
            
            for card in expiring_cards:
                pending_items.append({
                    'type': 'card',
                    'title': f"Card Expiring Soon",
                    'description': f"Card {card.card_number} expires {card.date_expires}",
                    'created': card.date_expires,
                    'url': f"/affiliationcard/admin/cards/{card.pk}/",
                })
        except:
            pass
    
    # CPD requirements for current user
    try:
        # Check if user needs CPD hours
        required_hours = 20  # Annual requirement
        if stats['cpd_hours'] < required_hours:
            pending_items.append({
                'type': 'cpd',
                'title': 'CPD Hours Required',
                'description': f"You need {required_hours - stats['cpd_hours']} more CPD hours this year",
                'created': timezone.now(),
                'url': '/cpd/activities/',
            })
    except:
        pass
    
    # ============================================================================
    # ROLE-BASED CUSTOMIZATION
    # ============================================================================
    
    # Add role-specific context
    role = getattr(user, 'role', None)
    user_role = getattr(role, 'title', 'Member') if role else 'Member'
    
    # Admin-specific stats
    if user.is_staff:
        stats['system_health'] = 99  # You can calculate this based on system metrics
        
        # Recent activities for admins
        try:
            recent_activities = []
            
            # Recent applications
            for model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                recent_apps = model.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).order_by('-created_at')[:3]
                
                for app in recent_apps:
                    recent_activities.append({
                        'description': f"New {model.__name__.replace('Application', '')} application from {app.full_names}",
                        'timestamp': app.created_at,
                    })
            
            # Sort by timestamp
            recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
            stats['recent_activities'] = recent_activities[:5]
            
        except:
            stats['recent_activities'] = []
    
    # ============================================================================
    # CONTEXT ASSEMBLY
    # ============================================================================
    
    context = {
        # Core content
        'announcements': announcements,
        'events': events,
        'projects': projects,
        
        # Statistics
        'stats': stats,
        
        # Attention items
        'pending_items': pending_items,
        
        # User context
        'user_role': user_role,
        'is_admin': user.is_staff,
        
        # System status
        'system_status': {
            'card_service': 'operational',
            'email_service': 'operational', 
            'verification_service': 'operational',
        }
    }
    
    return render(request, 'app/dashboard.html', context)


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
    qs = Projects.objects.filter(team_members=request.user) | Projects.objects.filter(manager=request.user)
    projects = qs.distinct()
    return render(request, 'app/project_list.html', {'projects': projects})

@login_required
def project_kanban(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    if request.user not in project.team_members.all() and request.user != project.manager:
        return HttpResponseForbidden()

    # Prepare tasks per status as a list of tuples for template friendly iteration
    tasks_by_status = []
    for key, label in Task.STATUS_CHOICES:
        tasks = project.tasks.filter(status=key).order_by('-priority', '-created_at')
        tasks_by_status.append((key, label, tasks))

    return render(request, 'workspace/kanban.html', {
        'project': project,
        'tasks_by_status': tasks_by_status,
        'form': TaskForm(initial={'project_task': project.id}),
    })


@login_required
def task_detail_ajax(request, pk):
    task = get_object_or_404(Task, pk=pk)
    data = {
        'title': task.title,
        'description': task.description,
        'due_date': task.due_date.strftime('%Y-%m-%d'),
        'status': task.get_status_display(),
        'assigned_to': task.assigned_to.get_full_name() if task.assigned_to else None,
        'attachment_url': task.attachment.url if task.attachment else None,
        'tags': [t.name for t in task.tags.all()],
        'priority': task.get_priority_display(),
    }
    return JsonResponse(data)

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            form.save()
            #notify_user(request.user, f'Project {proj.name} created.')
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
@permission_required('app.manage_projects', raise_exception=True)
def edit_project(request, project_id):
    proj=get_object_or_404(Projects,id=project_id)
    form=ProjectForm(request.POST or None, request.FILES or None, instance=proj)
    if form.is_valid():
        proj=form.save()
        #notify_user(request.user, f'Project {proj.name} updated.')
        messages.success(request,'Project updated.')
        return redirect('project_kanban', id=project_id)
    return render(request,'app/project_form.html',{'form':form,'project':proj})

@login_required
@permission_required('apps.manage_projects', raise_exception=True)
def delete_project(request, project_id):
    project = get_object_or_404(Projects, id=project_id)
    if request.method == 'POST':
        project.delete()
        #notify_user(request.user, f'Project {proj.name} deleted.')
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

@require_http_methods(["POST"])
@login_required
def create_task(request):
    form = TaskForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            task = form.save(commit=False)
            task.created_by = request.user
            task.status = form.cleaned_data.get('status', 'NOT_STARTED')
            task.save()
            form.save_m2m()  # Save tags
            
            return JsonResponse({
                'status': 'ok',
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'due_date': task.due_date.strftime('%Y-%m-%d')
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'error': form.errors}, status=400)

@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    return render(request, 'app/task_detail.html', {'task': task})

@require_http_methods(["POST"])
@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    form = TaskForm(request.POST, request.FILES, instance=task)
    if form.is_valid():
        try:
            task = form.save()
            return JsonResponse({
                'status': 'ok',
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'due_date': task.due_date.strftime('%Y-%m-%d')
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'error': form.errors}, status=400)

# Update delete_task view
@require_http_methods(["POST"])
@login_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    try:
        task.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=400)

@require_http_methods(["POST"])
@login_required
def move_task(request, pk):
    try:
        task = get_object_or_404(Task, pk=pk)
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in dict(Task.STATUS_CHOICES).keys():
            return JsonResponse({'status': 'error', 'error': 'Invalid status'}, status=400)
        
        task.status = new_status
        task.save()
        return JsonResponse({'status': 'ok'})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=400)

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



# Error Views

def error_404(request, exception):
    return render(request, 'error/404.html', status=404)

def error_500(request):
    return render(request, 'error/500.html', status=500)

def error_403(request, exception):
    return render(request, 'error/403.html', status=403)    

def error_400(request, exception):
    return render(request, 'error/400.html', status=400)
