from django.contrib import admin

from .models import Job, JobProduct, JobStaff


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
