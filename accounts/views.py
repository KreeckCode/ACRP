from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from .forms import UserRegistrationForm, UserUpdateForm
from .models import Department, Role, User


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
            return redirect('user_list')
    else:
        form = UserUpdateForm(instance=user)
    return render(request, 'accounts/update_user.html', {'form': form})


from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse

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

from .forms import RoleForm, DepartmentForm

@login_required
@permission_required('accounts.add_role', raise_exception=True)
def manage_roles(request):
    """
    View to create and edit roles.
    """
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Role saved successfully.')
            return redirect('accounts:manage_roles')
    else:
        form = RoleForm()

    roles = Role.objects.all()
    return render(request, 'accounts/manage_roles.html', {'form': form, 'roles': roles})


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
