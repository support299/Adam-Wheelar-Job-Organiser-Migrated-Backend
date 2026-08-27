import hashlib

from django.core.cache import cache
from rest_framework import generics
from rest_framework.response import Response

from .models import Activity
from .serializers import ActivitySerializer

CACHE_TTL = 300  # seconds
_VERSION_KEY = 'activities:cache_version'


def _cache_version():
    """Monotonic counter mixed into list keys; bumping it orphans every list entry."""
    version = cache.get(_VERSION_KEY)
    if version is None:
        cache.set(_VERSION_KEY, 1, None)
        return 1
    return version


def _bump_cache_version():
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 1, None)


def _list_cache_key(request):
    digest = hashlib.md5(request.META.get('QUERY_STRING', '').encode()).hexdigest()
    return f'activities:list:v{_cache_version()}:{digest}'


def _detail_cache_key(pk):
    return f'activities:detail:{pk}'


class ActivityListCreateView(generics.ListCreateAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def list(self, request, *args, **kwargs):
        key = _list_cache_key(request)
        data = cache.get(key)
        if data is None:
            data = super().list(request, *args, **kwargs).data
            cache.set(key, data, CACHE_TTL)
        return Response(data)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user)
        _bump_cache_version()


class ActivityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer

    def retrieve(self, request, *args, **kwargs):
        key = _detail_cache_key(kwargs['pk'])
        data = cache.get(key)
        if data is None:
            data = super().retrieve(request, *args, **kwargs).data
            cache.set(key, data, CACHE_TTL)
        return Response(data)

    def perform_update(self, serializer):
        serializer.save()
        _bump_cache_version()
        cache.delete(_detail_cache_key(self.kwargs['pk']))

    def perform_destroy(self, instance):
        instance.delete()
        _bump_cache_version()
        cache.delete(_detail_cache_key(self.kwargs['pk']))
