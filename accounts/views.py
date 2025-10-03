
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from .forms import ProfileEditForm, UserRegistrationForm, UserUpdateForm
from .models import Department, Role, User
from django.db.models import Q
from django.utils import timezone 
import logging
from django.contrib.auth import views as auth_views
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from django.urls import reverse_lazy
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
from .forms import RoleForm, DepartmentForm

logger = logging.getLogger(__name__)


@login_required
@permission_required('accounts.view_user_list', raise_exception=True)
def user_list(request):
    """
    View to display a list of all users in the system. Accessible to users with the 'view_user_list' permission.
    """
    users = User.objects.all()
    return render(request, 'accounts/user_list.html', {'users': users})

@login_required
@permission_required('accounts.add_user', raise_exception=True)
def register_user(request):
    """
    View for registering new users, allowing admins to assign roles and departments.
    """
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, 'User registered successfully.')
            return redirect('user_list')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register_user.html', {'form': form})


@login_required
@permission_required('accounts.change_user', raise_exception=True)
def update_user(request, user_id):
    """
    View for updating user profiles, allowing updates to roles, departments, and managers.
    """
    user = User.objects.get(pk=user_id)
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User updated successfully.')
            return redirect('accounts:user_list')
    else:
        form = UserUpdateForm(instance=user)
    return render(request, 'accounts/update_user.html', {'form': form})




@login_required
def change_password(request):
    """
    View to allow users to change their password.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep the user logged in
            messages.success(request, 'Your password was successfully updated!')
            return redirect(reverse('accounts:user_list'))
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def user_profile(request, user_id):
    """
    View to display detailed information about a user.
    """
    user = get_object_or_404(User, id=user_id)
    return render(request, 'accounts/user_profile.html', {'user': user})
    

    
@login_required
@permission_required('accounts.view_user_list', raise_exception=True)
def user_list(request):
    """
    View to display a list of all users with search and filtering options.
    """
    query = request.GET.get('q', '')
    role_filter = request.GET.get('role', '')
    department_filter = request.GET.get('department', '')

    users = User.objects.all()

    if query:
        users = users.filter(username__icontains=query)

    if role_filter:
        users = users.filter(role__title=role_filter)

    if department_filter:
        users = users.filter(department__name=department_filter)

    roles = Role.objects.all()
    departments = Department.objects.all()

    return render(request, 'accounts/user_list.html', {
        'users': users,
        'roles': roles,
        'departments': departments,
        'query': query,
        'role_filter': role_filter,
        'department_filter': department_filter,
    })

@login_required
@permission_required('accounts.view_user', raise_exception=True)
def get_user_details(request, user_id):
    """AJAX endpoint to get detailed user information."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    
    try:
        user = get_object_or_404(User, id=user_id)
        
        # Get user's subordinates (people they manage)
        subordinates = user.subordinates.all()
        subordinates_data = [
            {
                'id': sub.id,
                'name': sub.get_full_name,
                'username': sub.username,
                'role': sub.role.title if sub.role else 'No Role',
                'department': sub.department.name if sub.department else 'No Department'
            }
            for sub in subordinates
        ]
        
        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name,
                'email': user.email,
                'phone': user.phone,
                'employee_code': user.employee_code,
                'picture_url': user.get_picture(),
                'role': user.role.title if user.role else 'No Role',
                'department': user.department.name if user.department else 'No Department',
                'manager': user.manager.get_full_name if user.manager else 'No Manager',
                'acrp_role': user.get_acrp_role_display(),
                'date_joined': user.date_of_joining.strftime('%B %d, %Y'),
                'last_login': user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'Never',
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'subordinates_count': subordinates.count(),
                'subordinates': subordinates_data
            }
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    



@login_required
@permission_required('accounts.add_role', raise_exception=True)
def manage_roles(request):
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Role saved successfully.')
            return redirect('accounts:manage_roles')
    else:
        form = RoleForm()
    
    roles = Role.objects.all()
    return render(request, 'accounts/manage_roles.html', {
        'form': form, 
        'roles': roles
    })


@login_required
@permission_required('accounts.add_department', raise_exception=True)
def manage_departments(request):
    """
    View to create and edit departments.
    """
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department saved successfully.')
            return redirect('accounts:manage_departments')
    else:
        form = DepartmentForm()

    departments = Department.objects.all()
    return render(request, 'accounts/manage_departments.html', {'form': form, 'departments': departments})



class DebugPasswordResetView(auth_views.PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.txt'  # Plain text version
    html_email_template_name = 'registration/password_reset_email.html'  # HTML version
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')
    
    def form_valid(self, form):
        email = form.cleaned_data['email']
        
        # Debug logging
        logger.info(f"Password reset requested for email: {email}")
        print(f"DEBUG: Password reset requested for email: {email}")
        
        try:
            # Call parent form_valid (this sends the email)
            response = super().form_valid(form)
            
            return response
            
        except Exception as e:
            logger.error(f"Password reset email failed: {str(e)}")
            print(f"DEBUG ERROR: Password reset failed: {str(e)}")
            messages.error(self.request, f"Email sending failed: {str(e)}")
            return self.form_invalid(form)
    


@login_required
@permission_required('accounts.delete_role', raise_exception=True)
@require_http_methods(["POST"])
@csrf_protect
def delete_role(request, role_id):
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)
    
    try:
        role = get_object_or_404(Role, id=role_id)
        
        # Quick safety check
        if role.users.count() > 0:
            return JsonResponse({
                'success': False,
                'message': f'Cannot delete role "{role.title}". It is assigned to users.'
            })
        
        role_title = role.title
        role.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Role "{role_title}" deleted successfully.'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    


@login_required
@permission_required('accounts.view_role', raise_exception=True)
def check_role_dependencies(request, role_id):
    """
    Check what dependencies a role has before deletion.
    This can be called to show warnings before attempting deletion.
    
    Args:
        request: HTTP request object
        role_id: ID of the role to check
        
    Returns:
        JsonResponse with dependency information
    """
    try:
        role = get_object_or_404(Role, id=role_id)
        
        users_count = role.users.count()
        child_roles_count = role.child_roles.count()
        
        # Get specific users and child roles for detailed info
        users = list(role.users.values('id', 'username', 'first_name', 'last_name')[:10])  # Limit to 10 for performance
        child_roles = list(role.child_roles.values('id', 'title')[:10])  # Limit to 10 for performance
        
        can_delete = users_count == 0 and child_roles_count == 0
        
        return JsonResponse({
            'success': True,
            'can_delete': can_delete,
            'dependencies': {
                'users_count': users_count,
                'child_roles_count': child_roles_count,
                'users': users,
                'child_roles': child_roles,
                'has_more_users': users_count > 10,
                'has_more_child_roles': child_roles_count > 10
            },
            'warnings': [] if can_delete else [
                f'Role is assigned to {users_count} user(s)' if users_count > 0 else None,
                f'Role has {child_roles_count} subordinate role(s)' if child_roles_count > 0 else None
            ]
        })
        
    except Role.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Role not found.'
        }, status=404)
    

@login_required
@permission_required('accounts.delete_department', raise_exception=True)
@require_http_methods(["POST"])
@csrf_protect
def delete_department(request, department_id):
    """AJAX endpoint for deleting departments."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)
    
    try:
        department = get_object_or_404(Department, id=department_id)
        
        # Safety checks
        employees_count = department.employees.count()
        roles_count = department.roles.count()
        
        if employees_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Cannot delete department "{department.name}". It has {employees_count} employee(s). Please reassign them first.'
            })
        
        if roles_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Cannot delete department "{department.name}". It has {roles_count} role(s). Please reassign them first.'
            })
        
        with transaction.atomic():
            department_name = department.name
            department.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Department "{department_name}" has been successfully deleted.'
        })
        
    except Department.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Department not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'An unexpected error occurred.'}, status=500)
    

@login_required
@permission_required('accounts.view_department', raise_exception=True)
def get_department_details(request, department_id):
    """AJAX endpoint to get detailed department information."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    
    try:
        department = get_object_or_404(Department, id=department_id)
        
        # Get employees in this department
        employees = department.employees.select_related('role').all()
        employees_data = [
            {
                'id': emp.id,
                'name': emp.get_full_name,
                'username': emp.username,
                'email': emp.email,
                'role': emp.role.title if emp.role else 'No Role',
                'acrp_role': emp.get_acrp_role_display(),
                'is_active': emp.is_active
            }
            for emp in employees
        ]
        
        # Get roles in this department
        roles = department.roles.all()
        roles_data = [
            {
                'id': role.id,
                'title': role.title,
                'description': role.description,
                'users_count': role.users.count()
            }
            for role in roles
        ]
        
        return JsonResponse({
            'success': True,
            'department': {
                'id': department.id,
                'name': department.name,
                'description': department.description,
                'employees_count': employees.count(),
                'roles_count': roles.count(),
                'employees': employees_data,
                'roles': roles_data
            }
        })
        
    except Department.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    


@login_required
def my_profile(request):
    """
    User's own profile page - routes to appropriate profile view based on role.
    
    LEARNER role users see a student-focused profile.
    All other roles see a staff/admin profile with organizational hierarchy.
    """
    user = request.user
    
    # Route based on ACRP role
    if hasattr(user, 'acrp_role') and user.acrp_role == User.ACRPRole.LEARNER:
        return learner_profile_view(request)
    else:
        return staff_profile_view(request)


@login_required
def learner_profile_view(request):
    """
    Student/Learner profile page showing educational information,
    CPD progress, digital card status, and learning statistics.
    """
    user = request.user
    
    # ============================================================================
    # LEARNER BASIC INFO
    # ============================================================================
    
    profile_data = {
        'username': user.username,
        'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
        'email': user.email,
        'phone': user.phone or 'Not provided',
        'employee_code': user.employee_code or 'Not assigned',
        'picture_url': user.get_picture(),
        'date_joined': user.date_of_joining,
        'last_login': user.last_login,
        'acrp_role': user.get_acrp_role_display(),
    }
    
    # ============================================================================
    # APPLICATION STATUS
    # ============================================================================
    
    application_status = None
    try:
        from enrollments.models import AssociatedApplication, DesignatedApplication, StudentApplication
        
        for model in [StudentApplication, AssociatedApplication, DesignatedApplication]:
            application = model.objects.filter(
                Q(email=user.email) | Q(registration_number=user.username)
            ).select_related(
                'onboarding_session__selected_council',
                'onboarding_session__selected_affiliation_type'
            ).first()
            
            if application:
                application_status = {
                    'application_number': application.application_number,
                    'status': application.get_status_display(),
                    'status_class': application.status,
                    'council': application.onboarding_session.selected_council.name,
                    'council_code': application.onboarding_session.selected_council.code,
                    'affiliation_type': application.onboarding_session.selected_affiliation_type.name,
                    'submitted_at': application.submitted_at,
                    'approved_at': application.approved_at,
                }
                break
    except Exception as e:
        logger.warning(f"Could not fetch application for learner: {e}")
    
    # ============================================================================
    # DIGITAL CARD INFO
    # ============================================================================
    
    digital_card = None
    try:
        from affiliationcard.models import AffiliationCard
        
        card = AffiliationCard.objects.filter(
            Q(email=user.email) | Q(registration_number=user.username)
        ).first()
        
        if card:
            days_until_expiry = None
            if card.date_expires:
                days_until_expiry = (card.date_expires - timezone.now().date()).days
            
            digital_card = {
                'card_number': card.card_number,
                'status': card.get_status_display(),
                'status_class': card.status,
                'issue_date': card.date_issued,
                'expiry_date': card.date_expires,
                'days_until_expiry': days_until_expiry,
                'is_expiring_soon': days_until_expiry and days_until_expiry <= 30,
                'is_expired': days_until_expiry and days_until_expiry < 0,
                'card_url': f'/affiliationcard/cards/{card.pk}/',
            }
    except Exception as e:
        logger.warning(f"Could not fetch digital card: {e}")
    
    # ============================================================================
    # CPD SUMMARY
    # ============================================================================
    
    cpd_summary = {
        'current_year': timezone.now().year,
        'total_hours': 0,
        'required_hours': 20,
        'completion_percentage': 0,
        'status': 'incomplete',
    }
    
    try:
        from cpd.models import CPDRecord
        
        current_year = timezone.now().year
        approved_records = CPDRecord.objects.filter(
            user=user,
            completion_date__year=current_year,
            status='COMPLETED',
            approval__status='APPROVED'
        )
        
        total_hours = sum(
            float(record.hours_awarded or record.hours_claimed or 0)
            for record in approved_records
        )
        
        cpd_summary['total_hours'] = total_hours
        cpd_summary['completion_percentage'] = min(
            int((total_hours / cpd_summary['required_hours']) * 100), 100
        )
        cpd_summary['status'] = 'complete' if total_hours >= cpd_summary['required_hours'] else 'incomplete'
        
    except Exception as e:
        logger.warning(f"Could not fetch CPD data: {e}")
    
    # ============================================================================
    # QUICK STATS
    # ============================================================================
    
    quick_stats = [
        {
            'label': 'CPD Hours',
            'value': f"{cpd_summary['total_hours']}/{cpd_summary['required_hours']}",
            'icon': 'award',
            'color': 'purple',
        },
        {
            'label': 'Card Status',
            'value': digital_card['status'] if digital_card else 'No Card',
            'icon': 'credit-card',
            'color': 'green' if digital_card and digital_card['status_class'] == 'active' else 'gray',
        },
        {
            'label': 'Member Since',
            'value': user.date_of_joining.strftime('%Y'),
            'icon': 'calendar',
            'color': 'blue',
        },
    ]
    
    context = {
        'profile_data': profile_data,
        'application_status': application_status,
        'digital_card': digital_card,
        'cpd_summary': cpd_summary,
        'quick_stats': quick_stats,
        'page_title': 'My Profile',
        'is_learner': True,
    }
    
    return render(request, 'accounts/my_profile_learner.html', context)


@login_required
def staff_profile_view(request):
    """
    Staff/Admin profile page showing organizational hierarchy,
    permissions, role responsibilities, and team information.
    """
    user = request.user
    
    # ============================================================================
    # STAFF BASIC INFO
    # ============================================================================
    
    profile_data = {
        'username': user.username,
        'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
        'email': user.email,
        'phone': user.phone or 'Not provided',
        'employee_code': user.employee_code or 'Not assigned',
        'picture_url': user.get_picture(),
        'date_joined': user.date_of_joining,
        'last_login': user.last_login,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'is_active': user.is_active,
    }
    
    # ============================================================================
    # ORGANIZATIONAL INFO
    # ============================================================================
    
    org_info = {
        'role': user.role.title if user.role else 'No Role Assigned',
        'role_description': user.role.description if user.role else '',
        'department': user.department.name if user.department else 'No Department',
        'department_description': user.department.description if user.department else '',
        'manager': f"{user.manager.first_name} {user.manager.last_name}".strip() if user.manager else 'No Manager',
        'manager_id': user.manager.id if user.manager else None,
        'acrp_role': user.get_acrp_role_display(),
    }
    
    # ============================================================================
    # TEAM INFORMATION (Subordinates)
    # ============================================================================
    
    team_members = []
    if user.subordinates.exists():
        for subordinate in user.subordinates.select_related('role', 'department'):
            team_members.append({
                'id': subordinate.id,
                'name': f"{subordinate.first_name} {subordinate.last_name}".strip() or subordinate.username,
                'username': subordinate.username,
                'email': subordinate.email,
                'role': subordinate.role.title if subordinate.role else 'No Role',
                'department': subordinate.department.name if subordinate.department else 'No Department',
                'is_active': subordinate.is_active,
                'picture_url': subordinate.get_picture(),
            })
    
    # ============================================================================
    # PERMISSIONS SUMMARY
    # ============================================================================
    
    permissions_summary = {
        'can_manage_users': user.has_perm('accounts.change_user'),
        'can_manage_roles': user.has_perm('accounts.add_role'),
        'can_manage_departments': user.has_perm('accounts.add_department'),
        'can_approve_applications': user.has_perm('enrollments.change_baseapplication'),
        'can_manage_cpd': user.has_perm('cpd.change_cpdrecord'),
        'can_view_reports': user.is_staff,
    }
    
    # Count total permissions
    permissions_summary['total_permissions'] = sum(
        1 for perm in permissions_summary.values() if isinstance(perm, bool) and perm
    )
    
    # ============================================================================
    # RECENT ACTIVITY (placeholder for future implementation)
    # ============================================================================
    
    recent_activity = []
    # TODO: Track user actions in an audit log and display recent activities
    
    # ============================================================================
    # QUICK STATS
    # ============================================================================
    
    quick_stats = [
        {
            'label': 'Team Members',
            'value': len(team_members),
            'icon': 'users',
            'color': 'blue',
        },
        {
            'label': 'Role',
            'value': org_info['role'],
            'icon': 'briefcase',
            'color': 'purple',
        },
        {
            'label': 'Department',
            'value': org_info['department'],
            'icon': 'building',
            'color': 'green',
        },
        {
            'label': 'Permissions',
            'value': permissions_summary['total_permissions'],
            'icon': 'shield-check',
            'color': 'amber',
        },
    ]
    
    context = {
        'profile_data': profile_data,
        'org_info': org_info,
        'team_members': team_members,
        'permissions_summary': permissions_summary,
        'recent_activity': recent_activity,
        'quick_stats': quick_stats,
        'page_title': 'My Profile',
        'is_learner': False,
    }
    
    return render(request, 'accounts/my_profile_staff.html', context)


@login_required
def edit_profile(request):
    """
    Edit user's own profile information.
    Allows updating personal details, contact info, and profile picture.
    """
    user = request.user
    
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=user)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully.')
            return redirect('accounts:my_profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileEditForm(instance=user)
    
    context = {
        'form': form,
        'page_title': 'Edit Profile',
    }
    
    return render(request, 'accounts/edit_profile.html', context)