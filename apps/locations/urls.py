from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BaseLocationViewSet

router = DefaultRouter()
router.register(r'', BaseLocationViewSet, basename='location')

urlpatterns = [
    path('', include(router.urls)),
]
