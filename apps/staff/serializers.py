from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Staff


class StaffSerializer(serializers.ModelSerializer):
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = [
            'id', 'name', 'email', 'phone', 'role', 'active',
            'has_login', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'has_login', 'created_at', 'updated_at']

    def get_has_login(self, obj):
        return obj.user_id is not None


class CreateStaffAuthSerializer(serializers.Serializer):
    """Create or update the Django User linked to a Staff member."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value):
        validate_password(value)
        return value

    def save(self, staff: Staff):
        email = self.validated_data['email']
        password = self.validated_data['password']

        if staff.user:
            # Update existing linked user
            user = staff.user
            user.email = email
            user.username = email
            user.set_password(password)
            user.save()
            return {'ok': True, 'updated': True}

        # Try to find an existing User by email first
        user = User.objects.filter(email=email).first()
        if user:
            user.set_password(password)
            user.save()
        else:
            user = User.objects.create_user(username=email, email=email, password=password)

        staff.user = user
        staff.save(update_fields=['user'])
        return {'ok': True, 'updated': False}
