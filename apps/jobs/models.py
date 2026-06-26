import uuid

from django.db import models


class RecurrenceFrequency(models.TextChoices):
    WEEKLY = 'weekly', 'Weekly'
    BIWEEKLY = 'biweekly', 'Bi-Weekly'
    MONTHLY = 'monthly', 'Monthly'
    QUARTERLY = 'quarterly', 'Quarterly'
    SEMIANNUALLY = 'semiannually', 'Semi-Annually'
    ANNUALLY = 'annually', 'Annually'


class JobStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SCHEDULED = 'scheduled', 'Scheduled'
    COMPLETED = 'completed', 'Completed'
    SKIP = 'skip', 'Skip'
    NOT_INTERESTED = 'not_interested', 'Not Interested'


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    email = models.TextField(blank=True)
    phone = models.TextField(blank=True, null=True)
    service_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    address = models.TextField()
    lat = models.FloatField()
    lng = models.FloatField()
    service_date = models.DateField()
    service_time = models.TimeField()
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    notes = models.TextField(blank=True, null=True)
    is_recurring = models.BooleanField(default=False)
    frequency = models.CharField(
        max_length=20,
        choices=RecurrenceFrequency.choices,
        blank=True,
        null=True,
    )
    ghl_contact_id = models.TextField(blank=True, null=True)
    # Stable external key from the customer-list CSV ("ContactID" column).
    # Used to upsert rows so re-running the import never duplicates jobs.
    import_contact_id = models.TextField(blank=True, null=True, unique=True)
    service_type = models.TextField(default='installation')
    sale_date = models.DateField(blank=True, null=True)
    call_status = models.TextField(default='not_called')
    calls_made = models.IntegerField(default=0)
    color = models.TextField(blank=True, null=True)
    duration = models.IntegerField(default=60)
    parent_job = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='child_jobs',
    )
    occurrence_index = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['service_date', 'service_time']
        indexes = [
            models.Index(fields=['service_date']),
            models.Index(fields=['ghl_contact_id']),
            models.Index(fields=['import_contact_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.name} — {self.service_date}'


class JobStaff(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='job_staff')
    staff = models.ForeignKey('staff.Staff', on_delete=models.CASCADE, related_name='job_staff')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['job', 'staff']]
        indexes = [
            models.Index(fields=['staff']),
            models.Index(fields=['job']),
        ]

    def __str__(self):
        return f'{self.job_id} ↔ {self.staff_id}'


class JobProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='job_products')
    product = models.ForeignKey(
        'products.Product', on_delete=models.RESTRICT, related_name='job_products'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['job']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f'{self.job_id} — {self.product_id} × {self.quantity}'


class JobCompletion(models.Model):
    """Immutable snapshot written when a job is marked complete.

    Keeps history even when the parent job is updated or rolled forward
    (recurring jobs). job_id is a soft reference — no FK constraint.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.UUIDField(blank=True, null=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    service_date = models.DateField()
    service_time = models.TimeField(blank=True, null=True)
    service_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    name = models.TextField()
    email = models.TextField(blank=True)
    phone = models.TextField(blank=True, null=True)
    address = models.TextField()
    lat = models.FloatField(blank=True, null=True)
    lng = models.FloatField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    staff_ids = models.JSONField(default=list)
    product_lines = models.JSONField(default=list)
    service_type = models.TextField(default='installation')
    sale_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['job_id']),
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['-completed_at']),
        ]

    def __str__(self):
        return f'Completion {self.id} — {self.name} on {self.service_date}'
