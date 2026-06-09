from django.contrib import admin
from django.urls import include, path

from apps.ghl.views import GhlAuthorizeView, GhlCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),

    # GHL OAuth browser-redirect endpoints — paths must NOT contain "ghl"
    # (GHL Marketplace rejects redirect URIs that reference itself)
    path('api/oauth/authorize/', GhlAuthorizeView.as_view(), name='ghl-authorize'),
    path('api/oauth/callback/', GhlCallbackView.as_view(), name='ghl-callback'),

    # Auth
    path('api/auth/', include('apps.authentication.urls')),

    # Core resources
    path('api/jobs/', include('apps.jobs.urls')),
    path('api/completions/', include('apps.jobs.completion_urls')),
    path('api/staff/', include('apps.staff.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/plans/', include('apps.plans.urls')),
    path('api/job-progress/', include('apps.plans.progress_urls')),
    path('api/locations/', include('apps.locations.urls')),

    # Contacts and notes
    path('api/contacts/', include('apps.contacts.urls')),

    # GoHighLevel management + public webhook
    path('api/ghl/', include('apps.ghl.urls')),
    path('api/webhooks/', include('apps.ghl.webhook_urls')),

    # Google Maps proxy
    path('api/maps/', include('apps.maps.urls')),
]
