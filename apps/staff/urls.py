from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

from .views import StaffPayoutViewSet, StaffViewSet

# Registered as its own router and included first so 'payouts/' resolves
# here rather than being swallowed by StaffViewSet's '<pk>/' detail route.
# Must be a SimpleRouter, not DefaultRouter — DefaultRouter adds its own
# '^$' API-root view, which would then shadow GET /api/staff/ itself
# (matched before StaffViewSet's list route ever gets a chance).
payouts_router = SimpleRouter()
payouts_router.register(r'payouts', StaffPayoutViewSet, basename='staff-payout')

router = DefaultRouter()
router.register(r'', StaffViewSet, basename='staff')

urlpatterns = [
    path('', include(payouts_router.urls)),
    path('', include(router.urls)),
]
