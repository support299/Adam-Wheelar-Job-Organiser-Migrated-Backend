from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ContactNoteViewSet, GhlContactViewSet, GhlUserViewSet

router = DefaultRouter()
router.register(r'ghl', GhlContactViewSet, basename='ghl-contact')
router.register(r'ghl-users', GhlUserViewSet, basename='ghl-user')
router.register(r'notes', ContactNoteViewSet, basename='contact-note')

urlpatterns = [
    path('', include(router.urls)),
]
