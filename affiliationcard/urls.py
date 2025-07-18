from django.urls import path, include
from django.views.generic import RedirectView
from . import views

app_name = 'affiliationcard'

# ============================================================================
# PUBLIC VERIFICATION URLS - No authentication required
# ============================================================================
public_patterns = [
    # Main public verification page
    path('verify/', views.verify_lookup, name='verify_lookup'),
    
    # QR code verification (token-based)
    path('verify/<str:token>/', views.verify_token, name='verify_token'),
    
    # API endpoint for programmatic verification
    path('api/verify/', views.api_verify, name='api_verify'),
    
    # Secure card download with token
    path('download/<str:token>/', views.download_card, name='download_card'),
]

# ============================================================================
# ADMIN DASHBOARD AND MANAGEMENT URLS - Authentication required
# ============================================================================
admin_patterns = [
    # Main admin dashboard
    path('', views.card_dashboard, name='dashboard'),
    
    # Card assignment from external apps
    path('assign/<int:content_type_id>/<int:object_id>/', 
         views.assign_card, name='assign_card'),
    
    # Card list and detail views
    path('cards/', views.CardListView.as_view(), name='card_list'),
    path('cards/<int:pk>/', views.CardDetailView.as_view(), name='card_detail'),
    
    # Card operations
    path('cards/<int:pk>/update-status/', 
         views.update_card_status, name='update_card_status'),
    path('cards/<int:pk>/send/', views.send_card, name='send_card'),
    
    # Bulk operations
    path('bulk-operations/', views.bulk_operations, name='bulk_operations'),
]

# ============================================================================
# CARD TEMPLATE MANAGEMENT URLS - Admin only
# ============================================================================
template_patterns = [
    # Template list and management
    path('templates/', views.CardTemplateListView.as_view(), name='template_list'),
    path('templates/create/', views.CardTemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/', views.CardTemplateDetailView.as_view(), name='template_detail'),
    path('templates/<int:pk>/edit/', views.CardTemplateUpdateView.as_view(), name='template_update'),
    path('templates/<int:pk>/delete/', views.CardTemplateDeleteView.as_view(), name='template_delete'),
]

# ============================================================================
# ANALYTICS AND REPORTING URLS - Admin only
# ============================================================================
analytics_patterns = [
    # Analytics dashboard
    path('analytics/', views.analytics_dashboard, name='analytics'),
    
    # Report generation
    path('reports/', views.generate_report, name='generate_report'),
    path('reports/custom/', views.generate_report, name='custom_report'),
    
    # Export endpoints
    path('export/cards/', views.export_cards, name='export_cards'),
    path('export/verifications/', views.export_verifications, name='export_verifications'),
]

# ============================================================================
# SYSTEM ADMINISTRATION URLS - Superuser only
# ============================================================================
system_patterns = [
    # System settings
    path('settings/', views.system_settings, name='system_settings'),
    
    # System health and maintenance
    path('health/', views.system_health, name='system_health'),
    path('maintenance/', views.system_maintenance, name='system_maintenance'),
]

# ============================================================================
# API ENDPOINTS - For external integrations
# ============================================================================
api_patterns = [
    # Card verification API
    path('verify/', views.api_verify, name='api_verify'),
    
    # Card status API
    path('status/<str:card_number>/', views.api_card_status, name='api_card_status'),
    
    # Bulk verification API
    path('verify/bulk/', views.api_bulk_verify, name='api_bulk_verify'),
]

# ============================================================================
# MAIN URL PATTERNS
# ============================================================================
urlpatterns = [
    # Root redirect to dashboard for authenticated users, verify for anonymous
    path('', RedirectView.as_view(pattern_name='affiliationcard:dashboard'), name='root'),
    
    # Public verification endpoints (no 'admin' prefix)
    path('', include(public_patterns)),
    
    # Admin interface
    path('admin/', include(admin_patterns)),
    
    # Template management
    path('admin/', include(template_patterns)),
    
    # Analytics and reporting
    path('admin/', include(analytics_patterns)),
    
    # System administration
    path('admin/', include(system_patterns)),
    
    # API endpoints
    path('api/', include(api_patterns)),
]

# ============================================================================
# ALTERNATIVE URL PATTERNS (Commented out - choose one approach)
# ============================================================================
"""
# Alternative flat structure - uncomment if you prefer this approach
urlpatterns = [
    # Public endpoints
    path('', views.verify_lookup, name='verify_lookup'),
    path('verify/', views.verify_lookup, name='verify_lookup'),
    path('verify/<str:token>/', views.verify_token, name='verify_token'),
    path('download/<str:token>/', views.download_card, name='download_card'),
    
    # Admin dashboard
    path('dashboard/', views.card_dashboard, name='dashboard'),
    
    # Card management
    path('assign/<int:content_type_id>/<int:object_id>/', views.assign_card, name='assign_card'),
    path('cards/', views.CardListView.as_view(), name='card_list'),
    path('cards/<int:pk>/', views.CardDetailView.as_view(), name='card_detail'),
    path('cards/<int:pk>/update-status/', views.update_card_status, name='update_card_status'),
    path('cards/<int:pk>/send/', views.send_card, name='send_card'),
    path('bulk-operations/', views.bulk_operations, name='bulk_operations'),
    
    # Templates
    path('templates/', views.CardTemplateListView.as_view(), name='template_list'),
    path('templates/create/', views.CardTemplateCreateView.as_view(), name='template_create'),
    
    # Analytics
    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('reports/', views.generate_report, name='generate_report'),
    
    # System
    path('settings/', views.system_settings, name='system_settings'),
    
    # API
    path('api/verify/', views.api_verify, name='api_verify'),
]
"""
