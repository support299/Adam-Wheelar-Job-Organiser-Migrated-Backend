from rest_framework import serializers

from .models import Job, JobCompletion, JobProduct, JobStaff


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


class JobSerializer(serializers.ModelSerializer):
    staff_ids = serializers.SerializerMethodField()
    series_count = serializers.SerializerMethodField()
    occurrences = serializers.IntegerField(write_only=True, required=False, default=1, min_value=1)

    def get_staff_ids(self, obj):
        return [str(js.staff_id) for js in obj.job_staff.all()]

    def get_series_count(self, obj):
        if obj.parent_job_id is None and obj.occurrence_index == 1:
            return obj.child_jobs.count() + 1
        return None

    class Meta:
        model = Job
        fields = [
            'id', 'name', 'email', 'phone', 'service_value', 'address',
            'lat', 'lng', 'service_date', 'service_time', 'status', 'notes',
            'is_recurring', 'frequency', 'ghl_contact_id', 'service_type',
            'sale_date', 'call_status', 'calls_made', 'color', 'duration',
            'parent_job_id', 'occurrence_index', 'series_count', 'occurrences',
            'created_at', 'updated_at', 'staff_ids',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'staff_ids', 'series_count']


class JobStaffIdsSerializer(serializers.Serializer):
    staff_ids = serializers.ListField(child=serializers.UUIDField())


class JobCompletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCompletion
        fields = [
            'id', 'job_id', 'completed_at', 'service_date', 'service_time',
            'service_value', 'name', 'email', 'phone', 'address', 'lat', 'lng',
            'notes', 'staff_ids', 'product_lines', 'service_type', 'sale_date',
            'created_at',
        ]
        read_only_fields = ['id', 'completed_at', 'created_at']
