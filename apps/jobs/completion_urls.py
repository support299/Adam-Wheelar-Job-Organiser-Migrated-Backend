from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import JobCompletionViewSet

router = DefaultRouter()
router.register(r'', JobCompletionViewSet, basename='job-completion')

urlpatterns = [
    path('', include(router.urls)),
]
