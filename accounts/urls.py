from django.urls import path, include
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

urlpatterns = [
    path("", include("django.contrib.auth.urls")),
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
    # Password reset views
    path("password-reset/", PasswordResetView.as_view(template_name="registration/password_reset.html"), name="password_reset",),
    path("password-reset/done/",PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
