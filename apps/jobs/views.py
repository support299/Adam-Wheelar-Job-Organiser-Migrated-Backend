from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
    queryset = Job.objects.prefetch_related('job_staff').all()
    serializer_class = JobSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobFilter
    search_fields = ['name', 'email', 'address', 'phone']
    ordering_fields = ['service_date', 'service_time', 'created_at', 'status']
    ordering = ['service_date', 'service_time']
    # Returns a plain array unless ?page= is supplied (see OptionalPageNumberPagination).
    pagination_class = OptionalPageNumberPagination

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
