from django.urls import path
from . import views

app_name = "enrollments"
urlpatterns = [
    path("associated/",   views.associated_list,   name="associated_list"),
    path("associated/new/", views.associated_create, name="associated_create"),
    path("associated/<int:pk>/edit/", views.associated_update, name="associated_update"),
    path("associated/<int:pk>/approve/",views.associated_approve, name="associated_approve"),
    path("associated/<int:pk>/reject/",  views.associated_reject,  name="associated_reject"),
    path('associated/success/', views.associated_success, name='associated_success'),
    path('onboarding/',        views.onboarding,             name='onboarding'),
    path('onboarding/student/',views.learner_apply_prompt,   name='learner_apply_prompt'),
]
