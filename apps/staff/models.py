import uuid

from django.contrib.auth.models import User
from django.db import models


class StaffRole(models.TextChoices):
    USER = 'user', 'User'
    ADMIN = 'admin', 'Admin'


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    role = models.CharField(max_length=10, choices=StaffRole.choices, default=StaffRole.USER)
    active = models.BooleanField(default=True)
    color = models.TextField(blank=True, null=True)
    # Link to a Django auth User so this staff member can log in
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='staff_profile'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'staff'

    def __str__(self):
        return self.name


class StaffPayout(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='payouts')
    period_from = models.DateField()
    period_to = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_at']
        indexes = [
            models.Index(fields=['staff']),
        ]

    def __str__(self):
        return f'{self.staff_id} — ${self.amount} ({self.period_from} to {self.period_to})'
