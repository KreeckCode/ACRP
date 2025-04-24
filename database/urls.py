from django.urls import path
from . import views

app_name = "database"

urlpatterns = [
    path('my-db', views.DatabaseListView.as_view(), name='database_list'),
    path('add/', views.DatabaseCreateView.as_view(), name='database_add'),
    path('<int:pk>/', views.DatabaseDetailView.as_view(), name='database_detail'),
    path('<int:pk>/edit/', views.DatabaseUpdateView.as_view(), name='database_edit'),
    path('<int:pk>/delete/', views.DatabaseDeleteView.as_view(), name='database_delete'),
    path('<int:database_id>/entries/add/', views.EntryCreateView.as_view(), name='entry_add'),
    path('<int:database_id>/entries/', views.EntryListView.as_view(), name='entry_list'),
]
