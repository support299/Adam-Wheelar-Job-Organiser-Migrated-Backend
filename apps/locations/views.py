from rest_framework import filters, viewsets

from .models import BaseLocation
from .serializers import BaseLocationSerializer


class BaseLocationViewSet(viewsets.ModelViewSet):
    queryset = BaseLocation.objects.all()
    serializer_class = BaseLocationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address']
    ordering = ['name']
