from django.urls import path
from . import views

app_name = "enrollments"

urlpatterns = [
    # Onboarding and main entry points
    path('', views.onboarding, name='onboarding'),
    path('onboarding/', views.onboarding, name='onboarding_alt'),
    path('onboarding/student/', views.learner_apply_prompt, name='learner_apply_prompt'),
    
    # Administrative dashboard
    path('dashboard/', views.enrollment_dashboard, name='dashboard'),
    path('dash/', views.enrollment_dash, name='dash'),
    
    # CGMP Council URLs - Full CRUD
    path('cgmp/', views.cgmp_list, name='cgmp_list'),
    path('cgmp/new/', views.cgmp_create, name='cgmp_create'),
    path('cgmp/<int:pk>/', views.cgmp_detail, name='cgmp_detail'),
    path('cgmp/<int:pk>/edit/', views.cgmp_update, name='cgmp_update'),
    path('cgmp/<int:pk>/delete/', views.cgmp_delete, name='cgmp_delete'),
    
    # CPSC Council URLs - Full CRUD  
    path('cpsc/', views.cpsc_list, name='cpsc_list'),
    path('cpsc/new/', views.cpsc_create, name='cpsc_create'),
    path('cpsc/<int:pk>/', views.cpsc_detail, name='cpsc_detail'),
    path('cpsc/<int:pk>/edit/', views.cpsc_update, name='cpsc_update'),
    path('cpsc/<int:pk>/delete/', views.cpsc_delete, name='cpsc_delete'),
    
    # CMTP Council URLs - Full CRUD
    path('cmtp/', views.cmtp_list, name='cmtp_list'),
    path('cmtp/new/', views.cmtp_create, name='cmtp_create'),
    path('cmtp/<int:pk>/', views.cmtp_detail, name='cmtp_detail'),
    path('cmtp/<int:pk>/edit/', views.cmtp_update, name='cmtp_update'),
    path('cmtp/<int:pk>/delete/', views.cmtp_delete, name='cmtp_delete'),
    
    # Universal approval/rejection URLs
    path('<str:model_type>/<int:pk>/approve/', views.approve_application, name='approve_application'),
    path('<str:model_type>/<int:pk>/reject/', views.reject_application, name='reject_application'),
]