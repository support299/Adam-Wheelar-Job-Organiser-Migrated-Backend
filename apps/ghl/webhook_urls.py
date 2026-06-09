from django.urls import path

from .webhook_views import GhlWebhookView

urlpatterns = [
    path('ghl/', GhlWebhookView.as_view(), name='ghl-webhook'),
]
