import django_filters

from .models import Job, JobCompletion


class JobFilter(django_filters.FilterSet):
    service_date_from = django_filters.DateFilter(field_name='service_date', lookup_expr='gte')
    service_date_to = django_filters.DateFilter(field_name='service_date', lookup_expr='lte')
    status = django_filters.CharFilter(field_name='status')
    service_type = django_filters.CharFilter(field_name='service_type')
    ghl_contact_id = django_filters.CharFilter(field_name='ghl_contact_id')
    # Staff filter: jobs assigned to a specific staff member
    staff_id = django_filters.UUIDFilter(
        field_name='job_staff__staff__id', label='Staff ID'
    )

    class Meta:
        model = Job
        fields = ['status', 'service_type', 'ghl_contact_id']


class JobCompletionFilter(django_filters.FilterSet):
    service_date_from = django_filters.DateFilter(field_name='service_date', lookup_expr='gte')
    service_date_to = django_filters.DateFilter(field_name='service_date', lookup_expr='lte')
    service_type = django_filters.CharFilter(field_name='service_type')
    job_id = django_filters.UUIDFilter(field_name='job_id')

    class Meta:
        model = JobCompletion
        fields = ['service_type', 'job_id']
