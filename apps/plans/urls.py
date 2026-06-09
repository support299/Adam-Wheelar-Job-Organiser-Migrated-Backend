from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SavedPlanViewSet

router = DefaultRouter()
router.register(r'', SavedPlanViewSet, basename='plan')

urlpatterns = [
    path('', include(router.urls)),
]
