from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Staff
from .serializers import CreateStaffAuthSerializer, StaffSerializer


class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    ordering = ['name']

    @action(detail=False, methods=['post'], url_path='create-auth')
    def create_auth(self, request):
        email = request.data.get('email', '').strip().lower()
        staff = Staff.objects.filter(email__iexact=email).first()
        if not staff:
            return Response(
                {'skipped': True, 'message': f'No staff member found with email {email}.'},
                status=status.HTTP_200_OK,
            )
        serializer = CreateStaffAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(staff=staff)
        return Response({'skipped': False}, status=status.HTTP_200_OK)
