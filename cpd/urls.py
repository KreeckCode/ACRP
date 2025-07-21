from django.urls import path, include
from django.views.generic import RedirectView
from . import views

app_name = 'cpd'

# ============================================================================
# DASHBOARD PATTERNS - Main entry points
# ============================================================================
dashboard_patterns = [
    # Main dashboard - adaptive based on user role
    path('', views.dashboard, name='dashboard'),
    
    # Quick actions from dashboard
    path('quick-actions/', views.quick_actions, name='quick_actions'),
]

# ============================================================================
# ACTIVITY MANAGEMENT PATTERNS - Browse, search, create, manage
# ============================================================================
activity_patterns = [
    # Activity browsing and search
    path('activities/', views.ActivityListView.as_view(), name='activity_list'),
    path('activities/search/', views.ActivityListView.as_view(), name='activity_search'),
    
    # Activity detail and registration
    path('activities/<int:pk>/', views.ActivityDetailView.as_view(), name='activity_detail'),
    
    # Activity creation (role-based forms)
    path('activities/create/', views.ActivityCreateView.as_view(), name='activity_create'),
    path('activities/submit-external/', views.ActivityCreateView.as_view(), name='submit_external_activity'),
    
    # Quick registration for pre-approved activities
    path('activities/quick-register/', views.quick_register, name='quick_register'),
]

# ============================================================================
# USER PARTICIPATION PATTERNS - Personal CPD tracking
# ============================================================================
participation_patterns = [
    # Personal CPD records management
    path('my-records/', views.my_records, name='my_records'),
    path('my-records/export/', views.export_my_data, name='export_my_data'),
    
    # Individual record management
    path('records/<int:pk>/', views.record_detail, name='record_detail'),
    path('records/<int:pk>/edit/', views.record_detail, name='record_edit'),
    path('records/<int:pk>/evidence/', views.record_detail, name='upload_evidence'),
    path('records/<int:pk>/feedback/', views.record_detail, name='submit_feedback'),
    
    # User progress and compliance
    path('my-progress/', views.user_dashboard, name='my_progress'),
    path('my-compliance/', views.my_certificates, name='my_compliance'),
]

# ============================================================================
# APPROVAL WORKFLOW PATTERNS - Admin review and processing
# ============================================================================
approval_patterns = [
    # Approval queue management
    path('approvals/', views.approval_queue, name='approval_queue'),
    path('approvals/pending/', views.approval_queue, name='pending_approvals'),
    path('approvals/urgent/', views.approval_queue, name='urgent_approvals'),
    
    # Individual approval processing
    path('approvals/<int:pk>/', views.approval_detail, name='approval_detail'),
    path('approvals/<int:pk>/review/', views.approval_detail, name='review_approval'),
    
    # Bulk operations
    path('approvals/bulk/', views.bulk_approval, name='bulk_approval'),
    path('approvals/bulk-approve/', views.bulk_approval, name='bulk_approve'),
    path('approvals/bulk-reject/', views.bulk_approval, name='bulk_reject'),
]

# ============================================================================
# SYSTEM ADMINISTRATION PATTERNS - Admin-only management
# ============================================================================
admin_patterns = [
    # Provider management
    path('admin/providers/', views.CPDProviderListView.as_view(), name='provider_list'),
    path('admin/providers/create/', views.CPDProviderCreateView.as_view(), name='provider_create'),
    path('admin/providers/<int:pk>/', views.CPDProviderDetailView.as_view(), name='provider_detail'),
    path('admin/providers/<int:pk>/edit/', views.CPDProviderUpdateView.as_view(), name='provider_edit'),
    path('admin/providers/<int:pk>/delete/', views.CPDProviderDeleteView.as_view(), name='provider_delete'),
    
    # Category management
    path('admin/categories/', views.CPDCategoryListView.as_view(), name='category_list'),
    path('admin/categories/create/', views.CPDCategoryCreateView.as_view(), name='category_create'),
    path('admin/categories/<int:pk>/', views.CPDCategoryDetailView.as_view(), name='category_detail'),
    path('admin/categories/<int:pk>/edit/', views.CPDCategoryUpdateView.as_view(), name='category_edit'),
    path('admin/categories/<int:pk>/delete/', views.CPDCategoryDeleteView.as_view(), name='category_delete'),
    
    # Requirement management
    path('admin/requirements/', views.CPDRequirementListView.as_view(), name='requirement_list'),
    path('admin/requirements/create/', views.CPDRequirementCreateView.as_view(), name='requirement_create'),
    path('admin/requirements/<int:pk>/', views.CPDRequirementDetailView.as_view(), name='requirement_detail'),
    path('admin/requirements/<int:pk>/edit/', views.CPDRequirementUpdateView.as_view(), name='requirement_edit'),
    path('admin/requirements/<int:pk>/delete/', views.CPDRequirementDeleteView.as_view(), name='requirement_delete'),
    
    # Period management
    path('admin/periods/', views.CPDPeriodListView.as_view(), name='period_list'),
    path('admin/periods/create/', views.CPDPeriodCreateView.as_view(), name='period_create'),
    path('admin/periods/<int:pk>/', views.CPDPeriodDetailView.as_view(), name='period_detail'),
    path('admin/periods/<int:pk>/edit/', views.CPDPeriodUpdateView.as_view(), name='period_edit'),
    path('admin/periods/<int:pk>/delete/', views.CPDPeriodDeleteView.as_view(), name='period_delete'),
    path('admin/periods/<int:pk>/set-current/', views.set_current_period, name='set_current_period'),
    
    # Activity management (admin view)
    path('admin/activities/', views.AdminActivityListView.as_view(), name='admin_activity_list'),
    path('admin/activities/<int:pk>/edit/', views.AdminActivityUpdateView.as_view(), name='admin_activity_edit'),
    path('admin/activities/<int:pk>/delete/', views.AdminActivityDeleteView.as_view(), name='admin_activity_delete'),
    path('admin/activities/<int:pk>/approve/', views.admin_approve_activity, name='admin_approve_activity'),
    
    # User management (CPD-specific)
    path('admin/users/', views.UserComplianceListView.as_view(), name='user_compliance_list'),
    path('admin/users/<int:user_id>/compliance/', views.user_compliance_detail, name='user_compliance_detail'),
    path('admin/users/<int:user_id>/records/', views.admin_user_records, name='admin_user_records'),
    path('admin/users/<int:user_id>/override/', views.compliance_override, name='compliance_override'),
]

# ============================================================================
# ANALYTICS AND REPORTING PATTERNS - Data insights and exports
# ============================================================================
analytics_patterns = [
    # Analytics dashboards
    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('analytics/dashboard/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/compliance/', views.compliance_analytics, name='compliance_analytics'),
    path('analytics/activities/', views.activity_analytics, name='activity_analytics'),
    path('analytics/providers/', views.provider_analytics, name='provider_analytics'),
    
    # Report generation
    path('reports/', views.generate_report, name='generate_report'),
    path('reports/compliance/', views.generate_report, name='compliance_report'),
    path('reports/custom/', views.custom_report_builder, name='custom_report'),
    path('reports/scheduled/', views.scheduled_reports, name='scheduled_reports'),
    
    # Data exports
    path('exports/activities/', views.export_activities, name='export_activities'),
    path('exports/records/', views.export_records, name='export_records'),
    path('exports/compliance/', views.export_compliance, name='export_compliance'),
    path('exports/users/', views.export_users, name='export_users'),
]

# ============================================================================
# CERTIFICATE PATTERNS - Compliance certificates and verification
# ============================================================================
certificate_patterns = [
    # User certificate management
    path('certificates/', views.my_certificates, name='my_certificates'),
    path('certificates/download/<int:pk>/', views.download_certificate, name='download_certificate'),
    path('certificates/request/', views.request_certificate, name='request_certificate'),
    
    # Certificate generation (admin)
    path('admin/certificates/generate/', views.generate_certificates, name='generate_certificates'),
    path('admin/certificates/bulk-generate/', views.bulk_generate_certificates, name='bulk_generate_certificates'),
    
    # Public certificate verification
    path('verify/<uuid:token>/', views.verify_certificate, name='verify_certificate'),
    path('verify/', views.certificate_verification_form, name='certificate_verification'),
]

# ============================================================================
# API PATTERNS - AJAX endpoints and external integrations
# ============================================================================
api_v1_patterns = [
    # Activity API
    path('activities/search/', views.api_activity_search, name='api_activity_search'),
    path('activities/<int:pk>/details/', views.api_activity_details, name='api_activity_details'),
    path('activities/<int:pk>/register/', views.api_activity_register, name='api_activity_register'),
    
    # User progress API
    path('progress/', views.api_user_progress, name='api_user_progress'),
    path('progress/<int:user_id>/', views.api_user_progress, name='api_user_progress_detail'),
    path('compliance/', views.api_user_compliance, name='api_user_compliance'),
    path('compliance/<int:period_id>/', views.api_user_compliance, name='api_user_compliance_period'),
    
    # Admin statistics API
    path('stats/dashboard/', views.api_admin_stats, name='api_admin_stats'),
    path('stats/compliance/', views.api_compliance_stats, name='api_compliance_stats'),
    path('stats/activities/', views.api_activity_stats, name='api_activity_stats'),
    
    # Record management API
    path('records/', views.api_user_records, name='api_user_records'),
    path('records/<int:pk>/', views.api_record_detail, name='api_record_detail'),
    path('records/<int:pk>/status/', views.api_update_record_status, name='api_update_record_status'),
    
    # Evidence management API
    path('evidence/upload/', views.api_upload_evidence, name='api_upload_evidence'),
    path('evidence/<int:pk>/verify/', views.api_verify_evidence, name='api_verify_evidence'),
    
    # Approval workflow API
    path('approvals/', views.api_approval_queue, name='api_approval_queue'),
    path('approvals/<int:pk>/decision/', views.api_approval_decision, name='api_approval_decision'),
    path('approvals/bulk/', views.api_bulk_approval, name='api_bulk_approval'),
]

# API versioning
api_patterns = [
    path('v1/', include(api_v1_patterns)),
    # Future versions can be added here
    # path('v2/', include(api_v2_patterns)),
]

# ============================================================================
# UTILITY PATTERNS - Helper views and redirects
# ============================================================================
utility_patterns = [
    # Search and filtering helpers
    path('search/', views.global_search, name='global_search'),
    path('filters/categories/', views.get_categories_json, name='categories_json'),
    path('filters/providers/', views.get_providers_json, name='providers_json'),
    path('filters/activities/', views.get_activities_json, name='activities_json'),
    
    # Calendar and scheduling
    path('calendar/', views.cpd_calendar, name='cpd_calendar'),
    path('calendar/<int:year>/<int:month>/', views.cpd_calendar, name='cpd_calendar_month'),
    path('calendar/events.json', views.calendar_events_json, name='calendar_events_json'),
    
    # Notifications and reminders
    path('notifications/', views.user_notifications, name='notifications'),
    path('notifications/mark-read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Help and documentation
    path('help/', views.cpd_help, name='help'),
    path('help/<str:topic>/', views.cpd_help_topic, name='help_topic'),
    path('faq/', views.cpd_faq, name='faq'),
    
    # System health and maintenance
    path('health/', views.system_health, name='system_health'),
    path('maintenance/', views.maintenance_mode, name='maintenance'),
]

# ============================================================================
# WIZARD PATTERNS - Multi-step processes
# ============================================================================
wizard_patterns = [
    # Activity submission wizard
    path('wizard/submit-activity/', views.ActivitySubmissionWizard.as_view(), name='activity_submission_wizard'),
    path('wizard/submit-activity/<str:step>/', views.ActivitySubmissionWizard.as_view(), name='activity_submission_wizard_step'),
    
    # Compliance setup wizard (for new users)
    path('wizard/setup/', views.ComplianceSetupWizard.as_view(), name='compliance_setup_wizard'),
    path('wizard/setup/<str:step>/', views.ComplianceSetupWizard.as_view(), name='compliance_setup_wizard_step'),
    
    # Bulk import wizard (admin)
    path('wizard/import/', views.BulkImportWizard.as_view(), name='bulk_import_wizard'),
    path('wizard/import/<str:step>/', views.BulkImportWizard.as_view(), name='bulk_import_wizard_step'),
]

# ============================================================================
# MOBILE APP PATTERNS - Dedicated mobile API endpoints
# ============================================================================
mobile_api_patterns = [
    # Mobile authentication
    path('auth/login/', views.mobile_login, name='mobile_login'),
    path('auth/logout/', views.mobile_logout, name='mobile_logout'),
    path('auth/refresh/', views.mobile_refresh_token, name='mobile_refresh_token'),
    
    # Mobile dashboard
    path('dashboard/', views.mobile_dashboard, name='mobile_dashboard'),
    path('dashboard/summary/', views.mobile_dashboard_summary, name='mobile_dashboard_summary'),
    
    # Mobile activities
    path('activities/', views.mobile_activities, name='mobile_activities'),
    path('activities/<int:pk>/', views.mobile_activity_detail, name='mobile_activity_detail'),
    path('activities/<int:pk>/register/', views.mobile_register, name='mobile_register'),
    
    # Mobile records
    path('records/', views.mobile_records, name='mobile_records'),
    path('records/<int:pk>/', views.mobile_record_detail, name='mobile_record_detail'),
    path('records/upload-evidence/', views.mobile_upload_evidence, name='mobile_upload_evidence'),
    
    # Mobile certificates
    path('certificates/', views.mobile_certificates, name='mobile_certificates'),
    path('certificates/<int:pk>/download/', views.mobile_download_certificate, name='mobile_download_certificate'),
]

# ============================================================================
# INTEGRATION PATTERNS - External system integrations
# ============================================================================
integration_patterns = [
    # Webhook endpoints
    path('webhooks/provider-update/', views.provider_webhook, name='provider_webhook'),
    path('webhooks/activity-sync/', views.activity_sync_webhook, name='activity_sync_webhook'),
    path('webhooks/compliance-check/', views.compliance_check_webhook, name='compliance_check_webhook'),
    
    # External provider integrations
    path('integrations/providers/<str:provider_code>/activities/', 
          views.external_provider_activities, name='external_provider_activities'),
    path('integrations/providers/<str:provider_code>/sync/', 
          views.sync_provider_activities, name='sync_provider_activities'),
    
    # SSO and external authentication
    path('sso/callback/', views.sso_callback, name='sso_callback'),
    path('sso/metadata/', views.sso_metadata, name='sso_metadata'),
]

# ============================================================================
# MAIN URL PATTERNS - Organized by functionality
# ============================================================================
urlpatterns = [
    # Root redirect to dashboard
    path('', include(dashboard_patterns)),
    
    # Core functionality
    path('', include(activity_patterns)),
    path('', include(participation_patterns)),
    
    # Admin functionality (permission-protected in views)
    path('', include(approval_patterns)),
    path('', include(admin_patterns)),
    path('', include(analytics_patterns)),
    
    # Certificates and verification
    path('', include(certificate_patterns)),
    
    # API endpoints
    path('api/', include(api_patterns)),
    
    # Utility and helper views
    path('', include(utility_patterns)),
    
    # Multi-step wizards
    path('', include(wizard_patterns)),
    
    # Mobile app API (future use)
    path('mobile/', include(mobile_api_patterns)),
    
    # External integrations (future use)
    path('integrations/', include(integration_patterns)),
    
    # Legacy redirects and compatibility
    path('dashboard/', RedirectView.as_view(pattern_name='cpd:dashboard', permanent=True)),
    path('activities/browse/', RedirectView.as_view(pattern_name='cpd:activity_list', permanent=True)),
    path('my-cpd/', RedirectView.as_view(pattern_name='cpd:my_records', permanent=True)),
]


# ============================================================================
# ERROR HANDLING URL PATTERNS
# ============================================================================

# Custom error handlers for CPD app
handler404 = 'cpd.views.cpd_404'
handler403 = 'cpd.views.cpd_403'
handler500 = 'cpd.views.cpd_500'

# Development and testing URLs (only in DEBUG mode)
if settings.DEBUG:
    from django.conf import settings
    urlpatterns += [
        # Testing endpoints
        path('test/dashboard/', views.test_dashboard_data, name='test_dashboard'),
        path('test/compliance/', views.test_compliance_calculation, name='test_compliance'),
        path('test/notifications/', views.test_notifications, name='test_notifications'),
        
        # Sample data generation
        path('dev/sample-data/', views.generate_sample_data, name='generate_sample_data'),
        path('dev/reset-data/', views.reset_sample_data, name='reset_sample_data'),
    ]