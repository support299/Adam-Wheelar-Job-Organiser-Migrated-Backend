import calendar
from datetime import date, timedelta

from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response


def _add_frequency(d: date, frequency: str) -> date:
    if frequency == 'weekly':
        return d + timedelta(weeks=1)
    if frequency == 'biweekly':
        return d + timedelta(weeks=2)
    months_map = {'monthly': 1, 'quarterly': 3, 'semiannually': 6, 'annually': 12}
    if frequency in months_map:
        months = months_map[frequency]
        m = d.month - 1 + months
        year = d.year + m // 12
        month = m % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    return d

from apps.contacts.models import ContactNote
from apps.products.models import Product
from apps.staff.models import Staff
from config.pagination import OptionalPageNumberPagination

from .filters import JobCompletionFilter, JobFilter
from .models import Job, JobCompletion, JobProduct, JobStaff
from .serializers import (
    JobCompletionSerializer,
    JobProductLinesSerializer,
    JobProductWriteSerializer,
    JobSerializer,
    JobStaffIdsSerializer,
)


def _spawn_next_occurrence(completed_job: Job):
    """Create the next child job in a recurring series after one is completed."""
    root = completed_job if completed_job.parent_job_id is None else completed_job.parent_job
    total = root.total_occurrences
    if not total:
        return
    current_count = root.child_jobs.count() + 1
    if current_count >= total:
        return
    next_date = _add_frequency(completed_job.service_date, completed_job.frequency)
    next_index = (completed_job.occurrence_index or 1) + 1
    with transaction.atomic():
        next_job = Job.objects.create(
            name=root.name,
            email=root.email,
            phone=root.phone,
            ghl_contact_id=root.ghl_contact_id,
            service_value=root.service_value,
            address=root.address,
            lat=root.lat,
            lng=root.lng,
            service_date=next_date,
            service_time=root.service_time,
            status='pending',
            notes=None,
            is_recurring=True,
            frequency=root.frequency,
            service_type='servicing',
            call_status='not_called',
            calls_made=0,
            duration=root.duration,
            parent_job=root,
            occurrence_index=next_index,
            total_occurrences=total,
        )
        root_products = list(JobProduct.objects.filter(job=root))
        if root_products:
            JobProduct.objects.bulk_create([
                JobProduct(job=next_job, product_id=jp.product_id, quantity=jp.quantity, unit_price=jp.unit_price)
                for jp in root_products
            ])
        root_staff = list(JobStaff.objects.filter(job=root))
        if root_staff:
            JobStaff.objects.bulk_create([
                JobStaff(job=next_job, staff_id=js.staff_id)
                for js in root_staff
            ])


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.prefetch_related('job_staff', 'child_jobs').annotate(
        last_call_at=Subquery(
            ContactNote.objects.filter(job_id=OuterRef('id'))
            .order_by('-created_at')
            .values('created_at')[:1]
        )
    )
    serializer_class = JobSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobFilter
    search_fields = ['name', 'email', 'address', 'phone']
    ordering_fields = ['service_date', 'service_time', 'created_at', 'status']
    ordering = ['service_date', 'service_time']
    # Returns a plain array unless ?page= is supplied (see OptionalPageNumberPagination).
    pagination_class = OptionalPageNumberPagination

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        occurrences = serializer.validated_data.pop('occurrences', 1) or 1
        serializer.validated_data.pop('occurrence_index', None)
        validated = serializer.validated_data

        # Validate product_lines sent inline with the create request
        raw_lines = request.data.get('product_lines', [])
        if raw_lines:
            line_ser = JobProductWriteSerializer(data=raw_lines, many=True)
            line_ser.is_valid(raise_exception=True)
            product_lines = line_ser.validated_data
            product_ids = [l['product_id'] for l in product_lines]
            found = set(Product.objects.filter(id__in=product_ids).values_list('id', flat=True))
            missing = [str(p) for p in product_ids if p not in found]
            if missing:
                return Response({'detail': f'Products not found: {missing}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            product_lines = []

        # Validate staff_ids sent inline with the create request
        raw_staff = request.data.get('staff_ids', [])
        if raw_staff:
            staff_ser = JobStaffIdsSerializer(data={'staff_ids': raw_staff})
            staff_ser.is_valid(raise_exception=True)
            staff_ids = staff_ser.validated_data['staff_ids']
            found = set(Staff.objects.filter(id__in=staff_ids).values_list('id', flat=True))
            missing = [str(s) for s in staff_ids if s not in found]
            if missing:
                return Response({'detail': f'Staff not found: {missing}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            staff_ids = []

        def _bulk_assign(jobs):
            if product_lines:
                JobProduct.objects.bulk_create([
                    JobProduct(job=j, product_id=l['product_id'], quantity=l['quantity'], unit_price=l['unit_price'])
                    for j in jobs for l in product_lines
                ])
            if staff_ids:
                JobStaff.objects.bulk_create([
                    JobStaff(job=j, staff_id=sid)
                    for j in jobs for sid in staff_ids
                ])

        validated['occurrence_index'] = 1
        if validated.get('is_recurring') and validated.get('frequency') and occurrences > 1:
            validated['total_occurrences'] = occurrences

        with transaction.atomic():
            serializer.save()
            _bulk_assign([serializer.instance])

        job = serializer.instance
        if job.status in ('completed', 'skip') and job.is_recurring and job.total_occurrences:
            _spawn_next_occurrence(job)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_status = instance.status
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        occurrences = serializer.validated_data.pop('occurrences', None)
        serializer.save()

        # Update total_occurrences if manually changed on the parent job
        if (occurrences is not None
                and occurrences > 1
                and instance.parent_job_id is None
                and instance.occurrence_index == 1
                and instance.is_recurring
                and instance.frequency
                and instance.total_occurrences != occurrences):
            instance.total_occurrences = occurrences
            instance.save(update_fields=['total_occurrences'])

        # When a recurring job is completed or skipped, create the next occurrence
        if old_status not in ('completed', 'skip') and instance.status in ('completed', 'skip') and instance.is_recurring:
            _spawn_next_occurrence(instance)

        return Response(self.get_serializer(instance).data)

    # ── Staff assignment endpoints ─────────────────────────────────────────

    @action(detail=True, methods=['get', 'put'], url_path='staff')
    def staff(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            staff_ids = list(
                JobStaff.objects.filter(job=job).values_list('staff_id', flat=True)
            )
            return Response({'staff_ids': [str(s) for s in staff_ids]})

        serializer = JobStaffIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        staff_ids = serializer.validated_data['staff_ids']

        if staff_ids:
            found = set(Staff.objects.filter(id__in=staff_ids).values_list('id', flat=True))
            missing = [str(s) for s in staff_ids if s not in found]
            if missing:
                return Response(
                    {'detail': f'Staff not found: {missing}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            JobStaff.objects.filter(job=job).delete()
            if staff_ids:
                JobStaff.objects.bulk_create(
                    [JobStaff(job=job, staff_id=sid) for sid in staff_ids]
                )
        return Response({'staff_ids': [str(s) for s in staff_ids]})

    # ── Product (line item) endpoints ──────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='purchase-history')
    def purchase_history(self, request):
        """Return installation product rows with next-service info for a contact.

        Query params: email OR ghl_contact_id (at least one required).
        """
        email = request.query_params.get('email', '').strip().lower()
        ghl_contact_id = request.query_params.get('ghl_contact_id', '').strip()

        if not email and not ghl_contact_id:
            return Response(
                {'detail': 'Provide email or ghl_contact_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # All jobs belonging to this contact
        job_q = Q()
        if email:
            job_q |= Q(email__iexact=email)
        if ghl_contact_id:
            job_q |= Q(ghl_contact_id=ghl_contact_id)
        contact_jobs = Job.objects.filter(job_q)

        # Earliest pending/scheduled servicing job per product_id
        service_jobs = (
            contact_jobs
            .filter(service_type='servicing')
            .exclude(status__in=['completed', 'skip', 'not_interested'])
            .order_by('service_date')
            .prefetch_related('job_products')
        )
        next_service_by_product: dict = {}
        for j in service_jobs:
            for jp in j.job_products.all():
                pid = str(jp.product_id)
                if pid not in next_service_by_product:
                    next_service_by_product[pid] = j

        def next_svc_info(product_id: str, fallback_job=None) -> dict:
            svc = next_service_by_product.get(str(product_id))
            ref = svc or fallback_job
            return {
                'next_service_date': svc.service_date.isoformat() if svc else None,
                'next_service_status': svc.status if svc else None,
                'is_recurring': ref.is_recurring if ref else False,
                'frequency': ref.frequency if ref else None,
                'service_complete': svc is None,
            }

        rows = []

        # --- Installation completions ---
        # Derive emails to match completions (they don't store ghl_contact_id)
        completion_emails: set = set()
        if email:
            completion_emails.add(email)
        if ghl_contact_id:
            for e in (
                contact_jobs.exclude(email='')
                .values_list('email', flat=True)
                .distinct()
            ):
                completion_emails.add(e.lower())

        if completion_emails:
            email_q = Q()
            for e in completion_emails:
                email_q |= Q(email__iexact=e)
            install_completions = JobCompletion.objects.filter(
                email_q, service_type='installation'
            )
        else:
            install_completions = JobCompletion.objects.none()

        # --- Installation job products ---
        install_jobs = contact_jobs.filter(service_type='installation')
        install_job_products = (
            JobProduct.objects.filter(job__in=install_jobs)
            .select_related('product', 'job')
        )

        # Fetch original install jobs for completions (for is_recurring/frequency fallback)
        completion_job_ids = [c.job_id for c in install_completions if c.job_id]
        original_jobs_map = {
            str(j.id): j for j in Job.objects.filter(id__in=completion_job_ids)
        } if completion_job_ids else {}

        # Batch product name lookup
        all_product_ids: set = set()
        for c in install_completions:
            for line in (c.product_lines or []):
                pid = line.get('product_id')
                if pid:
                    all_product_ids.add(str(pid))
        for jp in install_job_products:
            all_product_ids.add(str(jp.product_id))

        product_name_map = {
            str(p.id): p.name
            for p in Product.objects.filter(id__in=all_product_ids)
        } if all_product_ids else {}

        for c in install_completions:
            original_job = original_jobs_map.get(str(c.job_id)) if c.job_id else None
            for i, line in enumerate(c.product_lines or []):
                pid = str(line.get('product_id', ''))
                qty = float(line.get('quantity', 0))
                price = float(line.get('unit_price', 0))
                rows.append({
                    'id': f'c-{c.id}-{i}',
                    'install_date': c.completed_at.isoformat(),
                    'install_status': 'completed',
                    'source': 'completion',
                    'address': c.address,
                    'product_id': pid,
                    'product_name': product_name_map.get(pid, 'Product'),
                    'quantity': str(qty),
                    'unit_price': str(price),
                    'total': str(round(qty * price, 2)),
                    **next_svc_info(pid, original_job),
                })

        for jp in install_job_products:
            qty = float(jp.quantity)
            price = float(jp.unit_price)
            rows.append({
                'id': f'j-{jp.id}',
                'install_date': jp.job.service_date.isoformat(),
                'install_status': jp.job.status,
                'source': 'job',
                'address': jp.job.address,
                'product_id': str(jp.product_id),
                'product_name': product_name_map.get(str(jp.product_id), 'Product'),
                'quantity': str(qty),
                'unit_price': str(price),
                'total': str(round(qty * price, 2)),
                **next_svc_info(str(jp.product_id), jp.job),
            })

        rows.sort(key=lambda r: r['install_date'], reverse=True)
        return Response(rows)

    @action(detail=False, methods=['get'], url_path='products')
    def list_all_products(self, request):
        lines = JobProduct.objects.select_related('product', 'job').all()
        ghl_contact_id = request.query_params.get('ghl_contact_id')
        if ghl_contact_id:
            lines = lines.filter(job__ghl_contact_id=ghl_contact_id)
        service_type = request.query_params.get('service_type')
        if service_type:
            lines = lines.filter(job__service_type=service_type)
        result = [
            {
                'id': str(jp.id),
                'job_id': str(jp.job_id),
                'product_id': str(jp.product_id),
                'quantity': str(jp.quantity),
                'unit_price': str(jp.unit_price),
                'created_at': jp.created_at.isoformat(),
            }
            for jp in lines
        ]
        return Response(result)

    @action(detail=True, methods=['get', 'put'], url_path='products')
    def products(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            lines = JobProduct.objects.filter(job=job).select_related('product')
            return Response([
                {
                    'id': str(jp.id),
                    'job_id': str(jp.job_id),
                    'product_id': str(jp.product_id),
                    'quantity': str(jp.quantity),
                    'unit_price': str(jp.unit_price),
                    'created_at': jp.created_at.isoformat(),
                }
                for jp in lines
            ])

        if isinstance(request.data, list):
            lines = request.data
        else:
            serializer = JobProductLinesSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            lines = serializer.validated_data['lines']

        line_serializer = JobProductWriteSerializer(data=lines, many=True)
        line_serializer.is_valid(raise_exception=True)
        lines = line_serializer.validated_data

        if lines:
            product_ids = [l['product_id'] for l in lines]
            found = set(Product.objects.filter(id__in=product_ids).values_list('id', flat=True))
            missing = [str(p) for p in product_ids if p not in found]
            if missing:
                return Response(
                    {'detail': f'Products not found: {missing}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            JobProduct.objects.filter(job=job).delete()
            if lines:
                JobProduct.objects.bulk_create([
                    JobProduct(
                        job=job,
                        product_id=l['product_id'],
                        quantity=l['quantity'],
                        unit_price=l['unit_price'],
                    )
                    for l in lines
                ])
        return Response({'detail': 'Products updated.'})


class JobCompletionViewSet(viewsets.ModelViewSet):
    queryset = JobCompletion.objects.all()
    serializer_class = JobCompletionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = JobCompletionFilter
    ordering_fields = ['completed_at', 'service_date']
    ordering = ['-completed_at']
