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
    
    # Secure card download with token - CRITICAL: This must be uncommented!
    path('download/<str:token>/', views.download_card, name='download_card'),
    
    # Optional: Download expired/invalid pages (you may need to create these views)
    # path('download/expired/', views.download_expired, name='download_expired'),
    # path('download/invalid/', views.download_invalid, name='download_invalid'),
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
    
    # Template management URLs
    path('templates/', views.CardTemplateListView.as_view(), name='template_list'),
    path('templates/create/', views.CardTemplateCreateView.as_view(), name='template_create'),
    
    # Analytics and reporting URLs
    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('reports/', views.generate_report, name='generate_report'),
    path('reports/custom/', views.generate_report, name='custom_report'),
    
    # System administration (if you have system_settings view)
    # path('settings/', views.system_settings, name='system_settings'),
]

# ============================================================================
# MAIN URL PATTERNS
# ============================================================================
urlpatterns = [
    # Redirect for root URL
    path('', RedirectView.as_view(pattern_name='affiliationcard:dashboard'), name='root'),
    
    # Public verification endpoints (includes download URLs)
    path('', include(public_patterns)),
    
    # Admin interface with all sub-patterns included
    path('admin/', include(admin_patterns)),
]