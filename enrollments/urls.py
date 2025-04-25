from django.urls import path
from . import views

app_name = "enrollments"
urlpatterns = [
    path("associated/",   views.associated_list,   name="associated_list"),
    path("associated/new/", views.associated_create, name="associated_create"),
    path("associated/<int:pk>/edit/", views.associated_update, name="associated_update"),
    path("associated/<int:pk>/approve/",views.associated_approve, name="associated_approve"),

    path("designated/",   views.designated_list,   name="designated_list"),
    path("designated/new/", views.designated_create, name="designated_create"),
    path("designated/<int:pk>/edit/", views.designated_update, name="designated_update"),
    path("designated/<int:pk>/approve/",views.designated_approve, name="designated_approve"),

    path("student/",      views.student_list,      name="student_list"),
    path("student/new/",  views.student_create,    name="student_create"),
    path("student/<int:pk>/edit/", views.student_update, name="student_update"),
    path("student/<int:pk>/approve/",views.student_approve,name="student_approve"),
]
