from django.urls import path
from . import views

app_name = 'cpd'

urlpatterns = [
    
    # ============================================================================
    # MAIN DASHBOARD
    # ============================================================================
    
    # Main CPD dashboard (adaptive based on user role)
    path('', views.dashboard, name='dashboard'),
    
    
    # ============================================================================
    # ACTIVITY MANAGEMENT
    # ============================================================================
    
    # Activity browsing and search
    path('activities/', views.ActivityListView.as_view(), name='activity_list'),
    path('activities/search/', views.ActivityListView.as_view(), name='activity_search'),
    
    # Activity details and registration
    path('activities/<int:pk>/', views.ActivityDetailView.as_view(), name='activity_detail'),
    
    # Create new activity (role-based form)
    path('activities/create/', views.ActivityCreateView.as_view(), name='activity_create'),
    
    # Quick registration for activities
    path('register/', views.quick_register, name='quick_register'),
    
    
    # ============================================================================
    # USER PARTICIPATION
    # ============================================================================
    
    # User's personal CPD records
    path('my-records/', views.my_records, name='my_records'),
    
    # Detailed record view with evidence upload
    path('records/<int:pk>/', views.record_detail, name='record_detail'),
    
    # Export user's personal data
    path('export/my-data/', views.export_my_data, name='export_my_data'),
    
    
    # ============================================================================
    # ADMIN WORKFLOWS (Approval Management)
    # ============================================================================
    
    # Approval queue management
    path('admin/approvals/', views.approval_queue, name='approval_queue'),
    
    # Detailed approval review
    path('admin/approvals/<int:pk>/', views.approval_detail, name='approval_detail'),
    
    # Bulk approval operations
    path('admin/approvals/bulk/', views.bulk_approval, name='bulk_approval'),
    
    
    # ============================================================================
    # ANALYTICS AND REPORTING
    # ============================================================================
    
    # Analytics dashboard
    path('admin/analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    
    # Report generation
    path('admin/reports/', views.generate_report, name='generate_report'),
    
    
    # ============================================================================
    # CERTIFICATES AND COMPLIANCE
    # ============================================================================
    
    # User's certificates dashboard
    path('certificates/', views.my_certificates, name='my_certificates'),
    
    # Download certificate PDF
    path('certificates/<int:pk>/download/', views.download_certificate, name='download_certificate'),
    
    # Public certificate verification (no login required)
    path('verify/<uuid:token>/', views.verify_certificate, name='verify_certificate'),
    
    
    # ============================================================================
    # API ENDPOINTS (AJAX)
    # ============================================================================
    
    # Activity search autocomplete
    path('api/search/', views.api_activity_search, name='api_activity_search'),
    
    # User progress data
    path('api/progress/', views.api_user_progress, name='api_user_progress'),
    
    # Admin statistics
    path('api/admin-stats/', views.api_admin_stats, name='api_admin_stats'),
    
    
    # ============================================================================
    # QUICK ACTIONS
    # ============================================================================
    
    # Quick action handler from dashboard
    path('quick-actions/', views.quick_actions, name='quick_actions'),
    
]