from django.contrib import admin

from .models import GhlToken, GhlWebhookLog


@admin.register(GhlToken)
class GhlTokenAdmin(admin.ModelAdmin):
    list_display = ['user_type', 'location_id', 'company_id', 'expires_at', 'updated_at']
    readonly_fields = ['id', 'created_at', 'updated_at', 'raw']


@admin.register(GhlWebhookLog)
class GhlWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['status', 'type', 'entity_id', 'entity_table', 'action', 'created_at']
    list_filter = ['status', 'entity_table']
    search_fields = ['entity_id', 'type', 'error']
    readonly_fields = ['id', 'created_at', 'payload']
