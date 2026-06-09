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
