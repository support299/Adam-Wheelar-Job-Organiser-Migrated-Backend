from rest_framework import serializers

from .models import JobProgress, SavedPlan


class SavedPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPlan
        fields = [
            'id', 'name', 'plan_date', 'base_id', 'base_name',
            'route_shape', 'optimize_metric', 'ordered_job_ids', 'staff_ids',
            'road_km', 'road_minutes', 'legs', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class JobProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobProgress
        fields = [
            'id', 'plan', 'job_id', 'staff_id', 'status',
            'actual_km', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UpsertJobProgressSerializer(serializers.Serializer):
    """Matches the current upsertJobProgress() behaviour: create-or-update
    on the (plan_id, job_id, staff_id) unique triple."""

    plan_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    staff_id = serializers.UUIDField()
    status = serializers.CharField(max_length=20, default='pending')
    actual_km = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_null=True, allow_blank=True)
