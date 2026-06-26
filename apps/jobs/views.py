import calendar
from datetime import date, timedelta

from django.db import transaction
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


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.prefetch_related('job_staff', 'child_jobs').all()
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

        if occurrences > 1 and validated.get('is_recurring') and validated.get('frequency'):
            child_jobs = []
            with transaction.atomic():
                current_date = validated['service_date']
                parent = Job.objects.create(**validated, occurrence_index=1)
                for i in range(1, occurrences):
                    current_date = _add_frequency(current_date, validated['frequency'])
                    child = Job.objects.create(
                        **{
                            **validated,
                            'service_date': current_date,
                            'status': 'pending',
                            'parent_job': parent,
                            'occurrence_index': i + 1,
                            'service_type': 'servicing',
                            'sale_date': None,
                        }
                    )
                    child_jobs.append(child)
                _bulk_assign([parent] + child_jobs)
            response_data = self.get_serializer(parent).data
            response_data['child_job_ids'] = [str(c.id) for c in child_jobs]
            return Response(response_data, status=status.HTTP_201_CREATED)

        with transaction.atomic():
            serializer.save()
            _bulk_assign([serializer.instance])
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        occurrences = serializer.validated_data.pop('occurrences', None)
        serializer.save()

        # Add more occurrences if parent job and count increased
        if (occurrences is not None
                and instance.parent_job_id is None
                and instance.occurrence_index == 1
                and instance.is_recurring
                and instance.frequency):
            current_count = instance.child_jobs.count() + 1
            extra = occurrences - current_count
            if extra > 0:
                last_child = instance.child_jobs.order_by('-occurrence_index').first()
                current_date = last_child.service_date if last_child else instance.service_date
                last_index = (last_child.occurrence_index or 1) if last_child else 1
                with transaction.atomic():
                    for i in range(extra):
                        current_date = _add_frequency(current_date, instance.frequency)
                        Job.objects.create(
                            name=instance.name,
                            email=instance.email,
                            phone=instance.phone,
                            ghl_contact_id=instance.ghl_contact_id,
                            service_value=instance.service_value,
                            address=instance.address,
                            lat=instance.lat,
                            lng=instance.lng,
                            service_date=current_date,
                            service_time=instance.service_time,
                            status='pending',
                            notes=instance.notes,
                            is_recurring=instance.is_recurring,
                            frequency=instance.frequency,
                            service_type='servicing',
                            call_status='not_called',
                            calls_made=0,
                            color=instance.color,
                            duration=instance.duration,
                            parent_job=instance,
                            occurrence_index=last_index + i + 1,
                        )

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

    @action(detail=False, methods=['get'], url_path='products')
    def list_all_products(self, request):
        lines = JobProduct.objects.select_related('product', 'job').all()
        ghl_contact_id = request.query_params.get('ghl_contact_id')
        if ghl_contact_id:
            lines = lines.filter(job__ghl_contact_id=ghl_contact_id)
        service_type = request.query_params.get('service_type')
        if service_type:
            lines = lines.filter(job__service_type=service_type)
        seen = set()
        result = []
        for jp in lines:
            if jp.product_id in seen:
                continue
            seen.add(jp.product_id)
            result.append({
                'id': str(jp.id),
                'job_id': str(jp.job_id),
                'product_id': str(jp.product_id),
                'quantity': str(jp.quantity),
                'unit_price': str(jp.unit_price),
                'created_at': jp.created_at.isoformat(),
            })
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
