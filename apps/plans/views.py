import csv

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job, JobProduct
from apps.jobs.views import _spawn_next_occurrence
from apps.staff.models import Staff
from .models import JobProgress, SavedPlan
from .serializers import (
    JobProgressSerializer,
    SavedPlanSerializer,
    UpsertJobProgressSerializer,
)


def _write_jobs_csv(response, job_rows, extra_headers=None):
    """job_rows: list of (job, extra_values) tuples. extra_headers: column names
    for extra_values, prepended before the standard job columns — used to tag
    each row with which plan it came from when exporting across many plans."""
    extra_headers = extra_headers or []
    jobs = [j for j, _ in job_rows]

    staff_ids = {str(js.staff_id) for j in jobs for js in j.job_staff.all()}
    staff_map = {str(s.id): s.name for s in Staff.objects.filter(id__in=staff_ids)}

    product_lines: dict = {}
    for jp in JobProduct.objects.filter(job__in=jobs).select_related('product'):
        product_lines.setdefault(str(jp.job_id), []).append(
            f'{jp.product.name} x{jp.quantity} @ ${jp.unit_price}'
        )

    writer = csv.writer(response)
    writer.writerow([
        *extra_headers,
        'Job Name', 'Contact ID', 'Email', 'Phone', 'Address', 'Latitude', 'Longitude',
        'Service Date', 'Service Time', 'Service Type', 'Status', 'Payment Status',
        'Amount', 'Assigned Staff', 'Products', 'Notes', 'Call Status', 'Calls Made',
        'Recurring', 'Frequency',
    ])
    for j, extra in job_rows:
        staff_names = ', '.join(
            staff_map.get(str(js.staff_id), '') for js in j.job_staff.all()
        )
        writer.writerow([
            *extra,
            j.name,
            j.ghl_contact_id or '',
            j.email,
            j.phone or '',
            j.address,
            j.lat,
            j.lng,
            j.service_date.isoformat(),
            j.service_time.strftime('%H:%M') if j.service_time else '',
            j.service_type,
            j.status,
            j.payment_status,
            j.service_value,
            staff_names,
            '; '.join(product_lines.get(str(j.id), [])),
            j.notes or '',
            j.call_status,
            j.calls_made,
            'Yes' if j.is_recurring else 'No',
            j.frequency or '',
        ])


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

    def _reschedule_jobs(self, job_ids):
        ids = [jid for jid in (job_ids or []) if jid]
        if ids:
            Job.objects.filter(id__in=ids, status='scheduled').update(status='rescheduled')

    def perform_create(self, serializer):
        plan_date = serializer.validated_data.get('plan_date')
        new_staff_ids = set(serializer.validated_data.get('staff_ids') or [])
        old_job_ids = set()
        if plan_date and new_staff_ids:
            for existing in SavedPlan.objects.filter(plan_date=plan_date):
                if new_staff_ids.intersection(existing.staff_ids or []):
                    old_job_ids.update(existing.ordered_job_ids or [])
                    existing.delete()
        plan = serializer.save()
        new_job_ids = set(plan.ordered_job_ids or [])
        # Only reschedule jobs that were in the old plan but removed from the new one
        self._reschedule_jobs(old_job_ids - new_job_ids)

    def perform_update(self, serializer):
        old_job_ids = set(serializer.instance.ordered_job_ids or [])
        plan = serializer.save()
        new_job_ids = set(plan.ordered_job_ids or [])
        # Only reschedule jobs that were removed from the plan (deselected)
        self._reschedule_jobs(old_job_ids - new_job_ids)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        job_map = self._job_map([instance])
        ctx = {**self.get_serializer_context(), 'job_map': job_map, 'current_staff_id': self._staff_ctx()}
        serializer = self.get_serializer(instance, context=ctx)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='export-csv')
    def export_csv(self, request, pk=None):
        plan = self.get_object()
        job_map = self._job_map([plan])
        job_rows = [
            (job_map[jid], [])
            for jid in (plan.ordered_job_ids or [])
            if jid in job_map
        ]

        response = HttpResponse(content_type='text/csv')
        filename = f"{plan.name}-{plan.plan_date}.csv".replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        _write_jobs_csv(response, job_rows)
        return response

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_all_csv(self, request):
        """Export jobs across every plan matching the current list filters
        (date_from/date_to/staff_id) — not just a single plan."""
        plans = list(self.filter_queryset(self.get_queryset()))
        job_map = self._job_map(plans)

        job_rows = [
            (job_map[jid], [plan.name, plan.plan_date.isoformat()])
            for plan in plans
            for jid in (plan.ordered_job_ids or [])
            if jid in job_map
        ]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="saved_plans.csv"'
        _write_jobs_csv(response, job_rows, extra_headers=['Plan Name', 'Plan Date'])
        return response


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
        new_status = d.get('status', 'pending')

        previous = JobProgress.objects.filter(
            plan_id=d['plan_id'], job_id=d['job_id'], staff_id=d['staff_id'],
        ).values_list('status', flat=True).first()

        obj, created = JobProgress.objects.update_or_create(
            plan_id=d['plan_id'],
            job_id=d['job_id'],
            staff_id=d['staff_id'],
            defaults={
                'status': new_status,
                'actual_km': d.get('actual_km'),
                'notes': d.get('notes'),
            },
        )

        # JobProgress.status values actually sent by the frontend are
        # pending/in_progress/done/cancelled (see jobProgress.ts) — "done" is
        # the completed signal, not "completed".
        job_status = None
        if new_status == 'done':
            job_status = 'completed'
        elif previous == 'done' and new_status == 'pending':
            job_status = 'rescheduled'
        elif new_status == 'cancelled':
            job_status = 'skip'

        if job_status:
            job = Job.objects.filter(id=d['job_id']).first()
            if job:
                old_job_status = job.status
                job.status = job_status
                job.save(update_fields=['status'])
                # Mirror JobViewSet.update(): spawn the next occurrence when a
                # recurring job transitions into completed/skip.
                if old_job_status not in ('completed', 'skip') and job.status in ('completed', 'skip') and job.is_recurring:
                    _spawn_next_occurrence(job)

        return Response(
            JobProgressSerializer(obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
