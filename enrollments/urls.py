from django.urls import path
from django.shortcuts import redirect
from . import views

app_name = 'enrollments'

urlpatterns = [
    
    path('onboarding/', views.onboarding_start, name='onboarding_start'),
    
    path('onboarding/council/<uuid:session_id>/', views.onboarding_council, name='onboarding_council'),
    
    path('onboarding/category/<uuid:session_id>/', views.onboarding_category, name='onboarding_category'),
    
    path('onboarding/subcategory/<uuid:session_id>/', views.onboarding_subcategory, name='onboarding_subcategory'),
    
    # ============================================================================
    # APPLICATION CREATION AND MANAGEMENT
    # ============================================================================
    
    # Create application based on onboarding session
    path('application/create/<uuid:session_id>/', views.application_create, name='application_create'),
    
    # Application detail views (unified for all types: associated, designated, student)
    path('application/<int:pk>/<str:app_type>/', views.application_detail, name='application_detail'),
    
    # Application update views
    path('application/<int:pk>/<str:app_type>/update/', views.application_update, name='application_update'),
    
    # Application list and search (admin view)
    path('applications/', views.application_list, name='application_list'),
    
    # ============================================================================
    # DASHBOARD URLS
    # ============================================================================
    
    # Admin enrollment dashboard
    path('dashboard/', views.enrollment_dashboard, name='enrollment_dashboard'),
    
    # Public application dashboard (shows status to applicants)
    path('dashboard/<int:pk>/<str:app_type>/', views.application_dashboard, name='application_dashboard'),
    
    # ============================================================================
    # APPLICATION REVIEW AND APPROVAL URLS
    # ============================================================================
    
    # Application review (for admin users)
    path('application/<int:pk>/<str:app_type>/review/', views.application_review, name='application_review'),
    
    # ============================================================================
    # AJAX ENDPOINTS FOR DYNAMIC FUNCTIONALITY
    # ============================================================================
    
    # Dynamic subcategory loading (for category selection)
    path('ajax/subcategories/', views.get_subcategories_ajax, name='get_subcategories_ajax'),
    
    # Application status checking (for real-time updates)
    path('ajax/status/<int:pk>/<str:app_type>/', views.application_status_ajax, name='application_status_ajax'),
    
    # ============================================================================
    # UTILITY AND LEGACY URLS
    # ============================================================================
    
    # Student application prompt (for token-based applications)
    path('learner-apply-prompt/', views.learner_apply_prompt, name='learner_apply_prompt'),
    
    # ============================================================================
    # LEGACY COMPATIBILITY URLS - Redirect to new flow
    # ============================================================================
    
    # Old onboarding URL (redirect to new flow)
    path('onboarding-old/', views.onboarding, name='onboarding_legacy'),
    
    # Legacy council-specific creation URLs (redirect to new onboarding)
    path('cgmp/create/', lambda request: redirect('enrollments:onboarding_start'), name='cgmp_create_legacy'),
    path('cpsc/create/', lambda request: redirect('enrollments:onboarding_start'), name='cpsc_create_legacy'), 
    path('cmtp/create/', lambda request: redirect('enrollments:onboarding_start'), name='cmtp_create_legacy'),
    
    # Legacy list views (redirect to unified application list)
    path('cgmp/', lambda request: redirect('enrollments:application_list'), name='cgmp_list_legacy'),
    path('cpsc/', lambda request: redirect('enrollments:application_list'), name='cpsc_list_legacy'),
    path('cmtp/', lambda request: redirect('enrollments:application_list'), name='cmtp_list_legacy'),
    
    # ============================================================================
    # ADMIN SHORTCUTS (Optional - for easier admin navigation)
    # ============================================================================
    
    # Quick links for admin users
    path('admin-dashboard/', views.enrollment_dashboard, name='admin_dashboard'),
    path('all-applications/', views.application_list, name='all_applications'),
]
