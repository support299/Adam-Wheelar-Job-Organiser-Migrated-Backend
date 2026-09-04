import uuid

from django.db import models


class RecurrenceFrequency(models.TextChoices):
    WEEKLY = 'weekly', 'Weekly'
    BIWEEKLY = 'biweekly', 'Bi-Weekly'
    MONTHLY = 'monthly', 'Monthly'
    QUARTERLY = 'quarterly', 'Quarterly'
    SEMIANNUALLY = 'semiannually', 'Semi-Annually'
    ANNUALLY = 'annually', 'Annually'


class ServiceType(models.TextChoices):
    INSTALLATION = 'installation', 'Installation'
    SERVICING = 'servicing', 'Servicing'
    AD_HOC = 'ad_hoc', 'Ad-hoc'
    WORKSHOP = 'workshop', 'Workshop'


class JobStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SCHEDULED = 'scheduled', 'Scheduled'
    COMPLETED = 'completed', 'Completed'
    SKIP = 'skip', 'Skip'
    NOT_INTERESTED = 'not_interested', 'Not Interested'
    RESCHEDULED = 'rescheduled', 'Rescheduled'


class PaymentStatus(models.TextChoices):
    UNPAID = 'unpaid', 'Unpaid'
    PAID = 'paid', 'Paid'


class CallOutcome(models.TextChoices):
    CONNECTED = 'connected', 'Connected'
    NOT_CONNECTED = 'not_connected', 'Not connected'
    CALL_BACK = 'call_back', 'Call back'
    NO_ANSWER = 'no_answer', 'No answer'


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField(blank=True)
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
    # Optional single activity classification, chosen from the Activity catalogue.
    activity = models.ForeignKey(
        'activities.Activity', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='jobs',
    )
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
    # True for backfilled rows created by import_activities_csv from the historic
    # CRM activity export. Re-running that command replaces the whole flagged set.
    is_imported = models.BooleanField(default=False)
    service_type = models.TextField(
        choices=ServiceType.choices, default=ServiceType.SERVICING
    )
    sale_date = models.DateField(blank=True, null=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PAID
    )
    call_status = models.TextField(default='not_called')
    calls_made = models.IntegerField(default=0)
    completed_at = models.DateTimeField(blank=True, null=True)
    duration = models.IntegerField(default=60)
    parent_job = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='child_jobs',
    )
    occurrence_index = models.IntegerField(null=True, blank=True)
    total_occurrences = models.IntegerField(null=True, blank=True, default=1000)
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


class JobCall(models.Model):
    """A single call logged against a job — either planned (no outcome yet) or
    already made. The UI shows all of a job's calls as one timeline."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='calls')
    date = models.DateField()
    notes = models.TextField(blank=True)
    outcome = models.CharField(
        max_length=20, choices=CallOutcome.choices, blank=True, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['job']),
        ]

    def __str__(self):
        return f'{self.job_id} — call {self.date}'


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
