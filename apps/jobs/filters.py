from datetime import date, timedelta

import django_filters

from .models import Job, JobCompletion


class JobFilter(django_filters.FilterSet):
    service_date_from = django_filters.DateFilter(field_name='service_date', lookup_expr='gte')
    service_date_to = django_filters.DateFilter(field_name='service_date', lookup_expr='lte')
    # Exact-date match (used by the Jobs List single-date picker)
    service_date = django_filters.DateFilter(field_name='service_date')
    status = django_filters.CharFilter(field_name='status')
    service_type = django_filters.CharFilter(field_name='service_type')
    ghl_contact_id = django_filters.CharFilter(field_name='ghl_contact_id')
    email = django_filters.CharFilter(field_name='email', lookup_expr='iexact')
    # Staff filter: jobs assigned to a specific staff member
    staff_id = django_filters.UUIDFilter(
        field_name='job_staff__staff__id', label='Staff ID'
    )
    # Jobs with no staff assigned (?unassigned=true)
    unassigned = django_filters.BooleanFilter(method='filter_unassigned')
    # Service-due bucket — mirrors getDueTag() on the frontend.
    due_tag = django_filters.CharFilter(method='filter_due_tag')

    class Meta:
        model = Job
        fields = ['status', 'service_type', 'ghl_contact_id']

    def filter_unassigned(self, queryset, name, value):
        if value:
            return queryset.filter(job_staff__isnull=True)
        return queryset

    def filter_due_tag(self, queryset, name, value):
        today = date.today()
        # getDueTag() returns null for completed jobs, so they never carry a tag.
        qs = queryset.exclude(status='completed')
        if value == 'overdue':
            return qs.filter(service_date__lt=today)
        if value == 'due_7':
            return qs.filter(service_date__gte=today, service_date__lte=today + timedelta(days=7))
        if value == 'due_15':
            return qs.filter(service_date__gt=today + timedelta(days=7), service_date__lte=today + timedelta(days=15))
        if value == 'due_30':
            return qs.filter(service_date__gt=today + timedelta(days=15), service_date__lte=today + timedelta(days=30))
        if value == 'due_60':
            return qs.filter(service_date__gt=today + timedelta(days=30), service_date__lte=today + timedelta(days=60))
        return queryset


class JobCompletionFilter(django_filters.FilterSet):
    service_date_from = django_filters.DateFilter(field_name='service_date', lookup_expr='gte')
    service_date_to = django_filters.DateFilter(field_name='service_date', lookup_expr='lte')
    service_type = django_filters.CharFilter(field_name='service_type')
    job_id = django_filters.UUIDFilter(field_name='job_id')

    class Meta:
        model = JobCompletion
        fields = ['service_type', 'job_id']
