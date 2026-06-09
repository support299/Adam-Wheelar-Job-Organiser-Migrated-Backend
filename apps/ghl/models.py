import uuid

from django.db import models


class GhlToken(models.Model):
    """Stores OAuth tokens for the GHL company and location connection.

    At most one row where location_id IS NULL (the company token).
    Each location has at most one row identified by location_id.
    Uniqueness for location rows is enforced by the unique constraint below.
    Company token uniqueness is enforced in the application layer (oauth.py).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    access_token = models.TextField()
    refresh_token = models.TextField(default='')
    expires_at = models.DateTimeField()
    location_id = models.TextField(blank=True, null=True)
    company_id = models.TextField(blank=True, null=True)
    user_type = models.TextField(blank=True, null=True)
    scope = models.TextField(blank=True, null=True)
    raw = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Enforce uniqueness of location_id for non-null values
            models.UniqueConstraint(
                fields=['location_id'],
                condition=models.Q(location_id__isnull=False),
                name='ghl_tokens_location_unique',
            ),
        ]

    def __str__(self):
        if self.location_id:
            return f'Location token: {self.location_id}'
        return f'Company token: {self.company_id}'


class GhlWebhookLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.TextField()
    type = models.TextField(blank=True, null=True)
    entity_id = models.TextField(blank=True, null=True)
    entity_table = models.TextField(blank=True, null=True)
    action = models.TextField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['entity_id']),
        ]

    def __str__(self):
        return f'[{self.status}] {self.type} — {self.entity_id}'
