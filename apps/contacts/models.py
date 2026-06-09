import uuid

from django.db import models


class GhlContact(models.Model):
    """Synced from GoHighLevel via webhook. id is GHL's own string ID."""

    id = models.CharField(primary_key=True, max_length=255)
    name = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    location_id = models.TextField(blank=True, null=True)
    user_id = models.TextField(blank=True, null=True)
    raw = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name or self.id


class GhlUser(models.Model):
    """Synced from GoHighLevel via webhook. id is GHL's own string ID."""

    id = models.CharField(primary_key=True, max_length=255)
    name = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    location_id = models.TextField(blank=True, null=True)
    raw = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name or self.id


class ContactNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # contact_key is a flexible string (GHL contact ID or email) — not a FK
    contact_key = models.TextField()
    # Soft reference to jobs — no FK constraint intentional
    job_id = models.UUIDField(blank=True, null=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contact_key']),
            models.Index(fields=['job_id']),
        ]

    def __str__(self):
        return f'Note {self.id} for {self.contact_key}'
