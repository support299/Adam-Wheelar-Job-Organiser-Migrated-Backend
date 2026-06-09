from django.contrib import admin

from .models import ContactNote, GhlContact, GhlUser


@admin.register(GhlContact)
class GhlContactAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'phone', 'location_id', 'updated_at']
    search_fields = ['name', 'email', 'phone', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(GhlUser)
class GhlUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'location_id', 'updated_at']
    search_fields = ['name', 'email', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ContactNote)
class ContactNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'contact_key', 'job_id', 'created_at']
    search_fields = ['contact_key', 'body']
    list_filter = []
