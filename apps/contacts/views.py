from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import ContactNote, GhlContact, GhlUser
from .serializers import ContactNoteSerializer, GhlContactSerializer, GhlUserSerializer


class GhlContactViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GhlContact.objects.all()
    serializer_class = GhlContactSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'phone']
    ordering = ['name']


class GhlUserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GhlUser.objects.all()
    serializer_class = GhlUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email']
    ordering = ['name']


class ContactNoteViewSet(viewsets.ModelViewSet):
    queryset = ContactNote.objects.all()
    serializer_class = ContactNoteSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['contact_key', 'job_id']
    ordering = ['-created_at']
