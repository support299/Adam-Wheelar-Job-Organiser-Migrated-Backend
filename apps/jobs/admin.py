from django.contrib import admin

from .models import Job, JobCompletion, JobProduct, JobStaff


class JobStaffInline(admin.TabularInline):
    model = JobStaff
    extra = 0


class JobProductInline(admin.TabularInline):
    model = JobProduct
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'service_date', 'service_time', 'status', 'service_type']
    list_filter = ['status', 'service_type', 'is_recurring']
    search_fields = ['name', 'email', 'phone', 'address']
    date_hierarchy = 'service_date'
    inlines = [JobStaffInline, JobProductInline]


@admin.register(JobCompletion)
class JobCompletionAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'service_date', 'service_type', 'service_value', 'completed_at']
    list_filter = ['service_type']
    search_fields = ['name', 'email', 'phone']
    date_hierarchy = 'service_date'
    readonly_fields = ['id', 'completed_at', 'created_at']
