from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Staff


@receiver(post_save, sender=Staff)
def sync_auth_user_role(sender, instance, **kwargs):
    if instance.user_id is None:
        return
    user = instance.user
    is_admin = instance.role == 'admin'
    if user.is_staff != is_admin:
        user.is_staff = is_admin
        user.save(update_fields=['is_staff'])


@receiver(post_delete, sender=Staff)
def delete_auth_user_on_staff_delete(sender, instance, **kwargs):
    if instance.user_id is None:
        return
    instance.user.delete()
