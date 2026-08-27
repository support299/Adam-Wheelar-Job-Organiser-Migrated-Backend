from django.db import models


class Activity(models.Model):
    # Free-text description of what happened — capped at 30 characters
    body = models.CharField(max_length=30)

    # Who logged it (Django auth user). Kept even if the user is deleted.
    created_by = models.ForeignKey(
        'auth.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='activities',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Activity {self.pk}'
