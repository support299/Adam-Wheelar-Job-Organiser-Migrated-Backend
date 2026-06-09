from rest_framework import serializers

from .models import BaseLocation


class BaseLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseLocation
        fields = ['id', 'name', 'address', 'lat', 'lng', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
