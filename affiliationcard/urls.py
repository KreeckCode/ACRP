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
    
]
