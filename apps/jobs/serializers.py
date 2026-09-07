from rest_framework import serializers

from .models import Job, JobCall, JobProduct, JobStaff


class DynamicFieldsMixin:
    """Honour ``?fields=a,b,c`` on read requests to return a sparse representation.

    Keeps list/detail payloads small for callers (Daily Planner, Map View) that
    only need a handful of columns. Ignored for writes and when the param is
    absent, so existing consumers keep getting the full record. ``id`` is always
    retained.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request is None or request.method not in ('GET', 'HEAD'):
            return
        raw = request.query_params.get('fields')
        if not raw:
            return
        wanted = {name.strip() for name in raw.split(',') if name.strip()}
        if not wanted:
            return
        wanted.add('id')
        for name in set(self.fields) - wanted:
            self.fields.pop(name)


class JobCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCall
        fields = ['id', 'job', 'date', 'notes', 'outcome', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class JobProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobProduct
        fields = ['id', 'product', 'quantity', 'unit_price', 'created_at']
        read_only_fields = ['id', 'created_at']


class JobProductWriteSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)


class JobProductLinesSerializer(serializers.Serializer):
    lines = JobProductWriteSerializer(many=True)


class JobSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    staff_ids = serializers.SerializerMethodField()
    series_count = serializers.SerializerMethodField()
    last_call_at = serializers.SerializerMethodField()
    occurrences = serializers.IntegerField(write_only=True, required=False, default=1, min_value=1)

    def get_staff_ids(self, obj):
        return [str(js.staff_id) for js in obj.job_staff.all()]

    def get_series_count(self, obj):
        if obj.parent_job_id is None and obj.occurrence_index == 1:
            return obj.child_jobs.count() + 1
        return None

    def get_last_call_at(self, obj):
        # Populated by the JobViewSet queryset annotation; None on unannotated instances
        value = getattr(obj, 'last_call_at', None)
        return value.isoformat() if value else None

    class Meta:
        model = Job
        fields = [
            'id', 'name', 'email', 'phone', 'service_value', 'address',
            'lat', 'lng', 'service_date', 'service_time', 'status', 'notes', 'activity',
            'is_recurring', 'frequency', 'ghl_contact_id', 'service_type',
            'sale_date', 'payment_status', 'call_status', 'calls_made', 'completed_at', 'duration',
            'parent_job_id', 'occurrence_index', 'total_occurrences', 'series_count', 'occurrences',
            'created_at', 'updated_at', 'staff_ids', 'last_call_at', 'is_imported',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'staff_ids', 'series_count', 'total_occurrences', 'last_call_at', 'is_imported']


class JobStaffIdsSerializer(serializers.Serializer):
    staff_ids = serializers.ListField(child=serializers.UUIDField())
