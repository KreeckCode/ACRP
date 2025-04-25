from django.contrib import admin
from django.urls import path, include
from django.conf.urls import handler404, handler500, handler400
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('app.urls')),
    path('auth/', include('accounts.urls')),
    path("acrpdevadmin/", admin.site.urls),
    path('finance/', include('finance.urls')),
    path('hr/', include('hr.urls')),
    path('app/', include('app.urls')),
    path('common/', include('common.urls')),
    path('db/', include('database.urls')),
    path('chat/', include('chat.urls')),
    path('providers/', include('providers.urls')),
    path('students/', include('student.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
    