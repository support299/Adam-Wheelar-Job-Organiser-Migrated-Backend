from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import JobProgress, SavedPlan
from .serializers import (
    JobProgressSerializer,
    SavedPlanSerializer,
    UpsertJobProgressSerializer,
)


class SavedPlanViewSet(viewsets.ModelViewSet):
    queryset = SavedPlan.objects.all()
    serializer_class = SavedPlanSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['plan_date']
    ordering_fields = ['plan_date', 'created_at']
    ordering = ['-plan_date', '-created_at']


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
