from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job
from .models import JobProgress, SavedPlan
from .serializers import (
    JobProgressSerializer,
    SavedPlanSerializer,
    UpsertJobProgressSerializer,
)


class SavedPlanViewSet(viewsets.ModelViewSet):
    serializer_class = SavedPlanSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['plan_date']
    ordering_fields = ['plan_date', 'created_at']
    ordering = ['-plan_date', '-created_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            qs = SavedPlan.objects.all()
        else:
            try:
                staff_id = str(user.staff_profile.id)
            except Exception:
                return SavedPlan.objects.none()
            qs = SavedPlan.objects.filter(staff_ids__contains=[staff_id])

        params = self.request.query_params
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        staff_filter = params.get('staff_id')

        if date_from:
            qs = qs.filter(plan_date__gte=date_from)
        if date_to:
            qs = qs.filter(plan_date__lte=date_to)
        if staff_filter and user.is_staff:
            qs = qs.filter(staff_ids__contains=[staff_filter])

        return qs.prefetch_related('progress')

    def _job_map(self, plans):
        all_ids = {jid for p in plans for jid in (p.ordered_job_ids or [])}
        jobs = Job.objects.prefetch_related('job_staff').filter(id__in=all_ids)
        return {str(j.id): j for j in jobs}

    def _staff_ctx(self):
        user = self.request.user
        if user.is_staff:
            return None
        profile = getattr(user, 'staff_profile', None)
        return str(profile.id) if profile else None

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        plans = list(page if page is not None else qs)
        job_map = self._job_map(plans)
        ctx = {**self.get_serializer_context(), 'job_map': job_map, 'current_staff_id': self._staff_ctx()}
        serializer = self.get_serializer(plans, many=True, context=ctx)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        plan_date = serializer.validated_data.get('plan_date')
        new_staff_ids = set(serializer.validated_data.get('staff_ids') or [])
        if plan_date and new_staff_ids:
            for existing in SavedPlan.objects.filter(plan_date=plan_date):
                if new_staff_ids.intersection(existing.staff_ids or []):
                    existing.delete()
        serializer.save()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        job_map = self._job_map([instance])
        ctx = {**self.get_serializer_context(), 'job_map': job_map, 'current_staff_id': self._staff_ctx()}
        serializer = self.get_serializer(instance, context=ctx)
        return Response(serializer.data)


class JobProgressViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = JobProgress.objects.all()
    serializer_class = JobProgressSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['plan', 'job_id', 'staff_id']


class UpsertJobProgressView(APIView):
    """Replicates the upsertJobProgress() server function:
    create or update a progress record on the (plan, job, staff) triple."""

    def post(self, request):
        serializer = UpsertJobProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        obj, created = JobProgress.objects.update_or_create(
            plan_id=d['plan_id'],
            job_id=d['job_id'],
            staff_id=d['staff_id'],
            defaults={
                'status': d.get('status', 'pending'),
                'actual_km': d.get('actual_km'),
                'notes': d.get('notes'),
            },
        )
        return Response(
            JobProgressSerializer(obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
