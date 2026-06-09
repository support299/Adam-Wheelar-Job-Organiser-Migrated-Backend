import uuid

from django.db import models


class SavedPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    plan_date = models.DateField()
    # Soft references to base_locations (no FK to keep plans self-contained)
    base_id = models.UUIDField(blank=True, null=True)
    base_name = models.TextField(blank=True, null=True)
    route_shape = models.TextField(default='round')
    optimize_metric = models.TextField(default='time')
    # JSON arrays of UUIDs/strings
    ordered_job_ids = models.JSONField(default=list)
    staff_ids = models.JSONField(default=list)
    road_km = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    road_minutes = models.IntegerField(blank=True, null=True)
    # Array of { distanceKm, minutes } objects
    legs = models.JSONField(default=list)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-plan_date', '-created_at']
        indexes = [
            models.Index(fields=['plan_date']),
        ]

    def __str__(self):
        return f'{self.name} — {self.plan_date}'


class JobProgressStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    EN_ROUTE = 'en_route', 'En Route'
    ON_SITE = 'on_site', 'On Site'
    COMPLETED = 'completed', 'Completed'
    SKIPPED = 'skipped', 'Skipped'
    ISSUE = 'issue', 'Issue'


class JobProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(SavedPlan, on_delete=models.CASCADE, related_name='progress')
    # Soft references — no FK to keep plans portable
    job_id = models.UUIDField()
    staff_id = models.UUIDField()
    status = models.CharField(
        max_length=20, choices=JobProgressStatus.choices, default=JobProgressStatus.PENDING
    )
    actual_km = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['plan', 'job_id', 'staff_id']]
        indexes = [
            models.Index(fields=['plan']),
            models.Index(fields=['job_id']),
            models.Index(fields=['staff_id']),
        ]

    def __str__(self):
        return f'Progress plan={self.plan_id} job={self.job_id} staff={self.staff_id}'
