from django.urls import path
from . import views

app_name = "providers"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    # Provider
    path("", views.provider_list, name="provider_list"),
    path("new/", views.provider_create, name="provider_create"),
    path("<int:pk>/", views.provider_detail, name="provider_detail"),
    path("<int:pk>/edit/", views.provider_update, name="provider_update"),
    path("<int:pk>/delete/", views.provider_delete, name="provider_delete"),
    # Accreditation
    path(
        "<int:provider_pk>/accreditations/new/",
        views.accreditation_create,
        name="accreditation_create",
    ),
    path(
        "<int:provider_pk>/accreditations/<int:pk>/edit/",
        views.accreditation_update,
        name="accreditation_update",
    ),
    path(
        "<int:provider_pk>/accreditations/<int:pk>/delete/",
        views.accreditation_delete,
        name="accreditation_delete",
    ),
    # Qualifications
    path(
        "<int:provider_pk>/qualifications/new/",
        views.qualification_create,
        name="qualification_create",
    ),
    path(
        "qualifications/<int:pk>/",
        views.qualification_detail,
        name="qualification_detail",
    ),
    path(
        "qualifications/<int:pk>/edit/",
        views.qualification_update,
        name="qualification_update",
    ),
    path(
        "qualifications/<int:pk>/delete/",
        views.qualification_delete,
        name="qualification_delete",
    ),
    # Modules
    path(
        "qualifications/<int:qualification_pk>/modules/new/",
        views.module_create,
        name="module_create",
    ),
    path("modules/<int:pk>/edit/", views.module_update, name="module_update"),
    path("modules/<int:pk>/delete/", views.module_delete, name="module_delete"),
    # Provider Users
    path(
        "<int:provider_pk>/users/", views.provider_user_list, name="provider_user_list"
    ),
    path(
        "<int:provider_pk>/users/new/",
        views.provider_user_create,
        name="provider_user_create",
    ),
    path(
        "<int:provider_pk>/users/<int:pk>/edit/",
        views.provider_user_update,
        name="provider_user_update",
    ),
    path(
        "<int:provider_pk>/users/<int:pk>/delete/",
        views.provider_user_delete,
        name="provider_user_delete",
    ),
    # Assessors
    path("<int:provider_pk>/assessors/", views.assessor_list, name="assessor_list"),
    path(
        "<int:provider_pk>/assessors/new/",
        views.assessor_create,
        name="assessor_create",
    ),
    path(
        "<int:provider_pk>/assessors/<int:pk>/edit/",
        views.assessor_update,
        name="assessor_update",
    ),
    path(
        "<int:provider_pk>/assessors/<int:pk>/delete/",
        views.assessor_delete,
        name="assessor_delete",
    ),
    # Documents
    path(
        "<int:provider_pk>/docs/upload/", views.document_upload, name="document_upload"
    ),
    path("docs/<int:doc_pk>/review/", views.document_review, name="document_review"),
    path("links/", views.link_list, name="link_list"),
    path("links/new/", views.link_create, name="link_create"),
    path("links/<int:pk>/edit/", views.link_update, name="link_update"),
]
