from django.contrib import admin

from .models import BaseLocation


@admin.register(BaseLocation)
class BaseLocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'lat', 'lng']
    search_fields = ['name', 'address']
