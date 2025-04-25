from django.urls import path
from . import views

app_name = 'provider'

urlpatterns = [
    path('',                 views.provider_list,    name='provider_list'),
    path('new/',             views.provider_create,  name='provider_create'),
    path('<int:pk>/',        views.provider_detail,  name='provider_detail'),
    path('<int:pk>/edit/',   views.provider_update,  name='provider_update'),
    path('<int:pk>/delete/', views.provider_delete,  name='provider_delete'),
    path('<int:provider_pk>/docs/upload/', views.document_upload, name='document_upload'),
    path('docs/<int:doc_pk>/review/',      views.document_review, name='document_review'),
]
