from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import JobProgressViewSet, UpsertJobProgressView

router = DefaultRouter()
router.register(r'', JobProgressViewSet, basename='job-progress')

urlpatterns = [
    path('upsert/', UpsertJobProgressView.as_view(), name='job-progress-upsert'),
    path('', include(router.urls)),
]
