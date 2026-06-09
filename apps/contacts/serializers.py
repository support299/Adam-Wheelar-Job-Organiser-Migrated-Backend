from rest_framework import serializers

from .models import ContactNote, GhlContact, GhlUser


class GhlContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = GhlContact
        fields = ['id', 'name', 'email', 'phone', 'type', 'location_id', 'user_id', 'created_at', 'updated_at']
        read_only_fields = fields


class GhlUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = GhlUser
        fields = ['id', 'name', 'email', 'phone', 'type', 'location_id', 'created_at', 'updated_at']
        read_only_fields = fields


class ContactNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactNote
        fields = ['id', 'contact_key', 'job_id', 'body', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
