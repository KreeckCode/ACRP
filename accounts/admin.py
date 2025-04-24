from django.contrib import admin
from .models import User, Role, Department, StaffUser


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'role', 'department', 'is_active')
    list_filter = ('role', 'department', 'is_active')
    search_fields = ('first_name', 'last_name', 'email', 'employee_code')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('title', 'description')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')


@admin.register(StaffUser)
class StaffUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'emergency_contact', 'date_of_birth')
