from rest_framework import serializers

from apps.jobs.serializers import JobSerializer
from .models import JobProgress, SavedPlan


class SavedPlanSerializer(serializers.ModelSerializer):
    jobs = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    def get_jobs(self, obj):
        job_map = self.context.get('job_map', {})
        current_staff_id = self.context.get('current_staff_id')  # None = admin, sees all
        result = []
        for jid in (obj.ordered_job_ids or []):
            job = job_map.get(str(jid))
            if not job:
                continue
            if current_staff_id:
                assigned = [str(js.staff_id) for js in job.job_staff.all()]
                if current_staff_id not in assigned:
                    continue
            result.append(JobSerializer(job, context=self.context).data)
        return result

    def get_progress(self, obj):
        return JobProgressSerializer(obj.progress.all(), many=True).data

    def validate(self, data):
        from apps.jobs.models import JobStaff
        job_ids = data.get('ordered_job_ids') or []
        if not job_ids:
            return data

        assignments = JobStaff.objects.filter(job_id__in=job_ids).values_list('job_id', 'staff_id')
        job_staff_map = {}
        for job_id, staff_id in assignments:
            job_staff_map.setdefault(str(job_id), set()).add(str(staff_id))

        all_staff_ids = set()
        has_unassigned = False
        for job_id in (str(jid) for jid in job_ids):
            ids = job_staff_map.get(job_id, set())
            if not ids:
                has_unassigned = True
            else:
                all_staff_ids.update(ids)

        if len(all_staff_ids) > 1:
            raise serializers.ValidationError(
                "All jobs in a plan must be assigned to the same staff member."
            )
        if has_unassigned and all_staff_ids:
            raise serializers.ValidationError(
                "Cannot mix assigned and unassigned jobs in the same plan."
            )
        return data

    class Meta:
        model = SavedPlan
        fields = [
            'id', 'name', 'plan_date', 'base_id', 'base_name',
            'route_shape', 'optimize_metric', 'ordered_job_ids', 'staff_ids',
            'road_km', 'road_minutes', 'legs', 'notes',
            'jobs', 'progress',
            'created_at', 'updated_at',
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
