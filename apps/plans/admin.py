from django.contrib import admin

from .models import JobProgress, SavedPlan


@admin.register(SavedPlan)
class SavedPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_date', 'road_km', 'road_minutes', 'created_at']
    date_hierarchy = 'plan_date'
    search_fields = ['name']


@admin.register(JobProgress)
class JobProgressAdmin(admin.ModelAdmin):
    list_display = ['plan', 'job_id', 'staff_id', 'status', 'updated_at']
    list_filter = ['status']
