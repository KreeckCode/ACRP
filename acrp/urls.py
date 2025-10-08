from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import handler404, handler500, handler400, handler403
from app.errors import health_check
from app.views import error_404, error_500, error_403, error_400
def trigger_error(request):
    division_by_zero = 1 / 0
    
urlpatterns = [
    path('', include('app.urls')),
    path('auth/', include('accounts.urls')),
    path("kreeck/", admin.site.urls),
    path('app/', include('app.urls')),
    path('card/', include('affiliationcard.urls')),
    path('cpd/', include('cpd.urls')),
    path('sentry-debug/', trigger_error),
    path('enrollments/', include('enrollments.urls')),
    path('health/', health_check, name='health_check'),
]
# Development-only routes
if settings.DEBUG:
    import debug_toolbar
    import django_browser_reload

    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
        path('__debug__/', include(debug_toolbar.urls)),
    ]
else:
    # Silence reload spam in production
    from django.http import HttpResponse
    urlpatterns += [
        path("__reload__/events/", lambda request: HttpResponse(status=204)),
    ]

# Custom error handlers
handler404 = error_404
handler500 = error_500
handler403 = error_403
handler400 = error_400

# Static & media handling
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
