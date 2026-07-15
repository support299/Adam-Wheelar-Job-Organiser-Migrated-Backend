from django.urls import path

from .views import (
    GhlConfigView,
    GhlExchangeView,
    GhlRefreshView,
    GhlStatusView,
    GhlSyncContactsView,
    GhlUpdateContactView,
)

urlpatterns = [
    path('config/', GhlConfigView.as_view(), name='ghl-config'),
    path('status/', GhlStatusView.as_view(), name='ghl-status'),
    path('exchange/', GhlExchangeView.as_view(), name='ghl-exchange'),
    path('refresh/', GhlRefreshView.as_view(), name='ghl-refresh'),
    path('sync-contacts/', GhlSyncContactsView.as_view(), name='ghl-sync-contacts'),
    path('update/user_id', GhlUpdateContactView.as_view(), name='ghl-update-contact'),
]
