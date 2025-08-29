from django.urls import path, include, reverse_lazy
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from . import views
from django.contrib.auth.views import LoginView
from django.contrib.auth import views as auth_views
from accounts.views import DebugPasswordResetView
app_name = 'accounts'

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # User management URLs
    path("register/", views.register_user, name="register_user"),
    path("update/<int:user_id>/", views.update_user, name="update_user"),
    path("list/", views.user_list, name="user_list"),
    path("change_password/", views.change_password, name="change_password"),
    # Role and department management URLs
    path("manage_roles/", views.manage_roles, name="manage_roles"),
    path("manage_departments/", views.manage_departments, name="manage_departments"),
    
    path('password-reset/', DebugPasswordResetView.as_view(), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
        extra_context={'title': 'Password Reset Email Sent'}
    ), name='password_reset_done'),

    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete'),
        extra_context={'title': 'Set Your New ACRP Password'}
    ), name='password_reset_confirm'),

    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
        extra_context={'title': 'Password Reset Successful'}
    ), name='password_reset_complete'),
]
