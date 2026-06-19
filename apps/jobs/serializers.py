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
    class Meta:
        model = Job
        fields = [
            'id', 'name', 'email', 'phone', 'service_value', 'address',
            'lat', 'lng', 'service_date', 'service_time', 'status', 'notes',
            'is_recurring', 'frequency', 'ghl_contact_id', 'service_type',
            'sale_date', 'call_status', 'calls_made', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


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
