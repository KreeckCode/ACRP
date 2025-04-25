from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    # LearnerProfile
    path('learners/',        views.learner_list,   name='learner_list'),
    path('learners/new/',    views.learner_create, name='learner_create'),
    path('learners/<int:pk>/',      views.learner_detail, name='learner_detail'),
    path('learners/<int:pk>/edit/', views.learner_update, name='learner_update'),
    path('learners/<int:pk>/delete/', views.learner_delete, name='learner_delete'),

    # AcademicHistory (nested under learner)
    path('learners/<int:learner_pk>/academics/new/', views.academic_create, name='academic_create'),
    # ... add the other CRUD routes here similarly
]
