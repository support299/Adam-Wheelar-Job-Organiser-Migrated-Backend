from django.contrib import admin

from .models import Staff


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'role', 'active']
    list_filter = ['role', 'active']
    search_fields = ['name', 'email', 'phone']
