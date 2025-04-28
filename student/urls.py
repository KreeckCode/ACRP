from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    # LearnerProfile
    path('',                       views.learner_list,        name='learner_list'),
    path('new/',                   views.learner_create,      name='learner_create'),
    path('<int:pk>/',              views.learner_detail,      name='learner_detail'),
    path('<int:pk>/edit/',         views.learner_update,      name='learner_update'),
    path('<int:pk>/delete/',       views.learner_delete,      name='learner_delete'),

    # AcademicHistory
    path('<int:learner_pk>/academics/',              views.academic_list,   name='academic_list'),
    path('<int:learner_pk>/academics/new/',          views.academic_create, name='academic_create'),
    path('<int:learner_pk>/academics/<int:pk>/edit/',views.academic_update, name='academic_update'),
    path('<int:learner_pk>/academics/<int:pk>/delete/', views.academic_delete, name='academic_delete'),

    # Enrollment
    path('<int:learner_pk>/enrollments/',              views.enrollment_list,   name='enrollment_list'),
    path('<int:learner_pk>/enrollments/new/',          views.enrollment_create, name='enrollment_create'),
    path('<int:learner_pk>/enrollments/<int:pk>/edit/',views.enrollment_update, name='enrollment_update'),
    path('<int:learner_pk>/enrollments/<int:pk>/delete/',views.enrollment_delete, name='enrollment_delete'),

    # CPD Events (global)
    path('cpd/events/',           views.cpd_event_list,    name='cpd_event_list'),
    path('cpd/events/new/',       views.cpd_event_create,  name='cpd_event_create'),
    path('cpd/events/<int:pk>/',  views.cpd_event_detail,  name='cpd_event_detail'),
    path('cpd/events/<int:pk>/edit/', views.cpd_event_update, name='cpd_event_update'),
    path('cpd/events/<int:pk>/delete/', views.cpd_event_delete, name='cpd_event_delete'),

    # CPD History
    path('<int:learner_pk>/cpd/history/',           views.cpd_history_list,    name='cpd_history_list'),
    path('<int:learner_pk>/cpd/history/new/',       views.cpd_history_create,  name='cpd_history_create'),
    path('<int:learner_pk>/cpd/history/<int:pk>/edit/', views.cpd_history_update, name='cpd_history_update'),
    path('<int:learner_pk>/cpd/history/<int:pk>/delete/', views.cpd_history_delete, name='cpd_history_delete'),

    # Affiliations
    path('<int:learner_pk>/affiliations/',           views.affiliation_list,   name='affiliation_list'),
    path('<int:learner_pk>/affiliations/new/',       views.affiliation_create, name='affiliation_create'),
    path('<int:learner_pk>/affiliations/<int:pk>/edit/', views.affiliation_update, name='affiliation_update'),
    path('<int:learner_pk>/affiliations/<int:pk>/delete/', views.affiliation_delete, name='affiliation_delete'),

    # Document Types (global)
    path('document-types/',       views.document_type_list,   name='document_type_list'),
    path('document-types/new/',   views.document_type_create, name='document_type_create'),
    path('document-types/<int:pk>/edit/', views.document_type_update, name='document_type_update'),
    path('document-types/<int:pk>/delete/', views.document_type_delete, name='document_type_delete'),

    # Learner Documents
    path('<int:learner_pk>/documents/',          views.learner_document_list,   name='learner_document_list'),
    path('<int:learner_pk>/documents/upload/',   views.learner_document_upload, name='learner_document_upload'),
    path('documents/<int:pk>/review/',           views.learner_document_review, name='learner_document_review'),
    path('apply/<uuid:token>/', views.learner_apply, name='learner_apply'),
]
