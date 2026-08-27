from django.urls import path

from . import views

urlpatterns = [
    path('activities', views.ActivityListCreateView.as_view(), name='activity_list_create'),
    path('activities/<int:pk>', views.ActivityDetailView.as_view(), name='activity_detail'),
]
