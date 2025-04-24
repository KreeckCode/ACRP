from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_room_list, name='chat_room_list'),
    path('room/<int:room_id>/', views.chat_room_detail, name='chat_room_detail'),
    path('create/', views.chat_room_create, name='chat_room_create'),
    path('delete/<int:room_id>/', views.chat_room_delete, name='chat_room_delete'),
]
