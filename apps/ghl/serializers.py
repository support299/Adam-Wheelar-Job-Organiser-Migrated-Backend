from rest_framework import serializers


class ExchangeCodeSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.URLField()


class UpdateContactCustomFieldSerializer(serializers.Serializer):
    contact_id = serializers.CharField()
    first_name = serializers.CharField(required=False, allow_blank=True)
    customData = serializers.DictField()

    def validate_customData(self, value):
        if not value.get('name'):
            raise serializers.ValidationError('customData.name is required.')
        return value


class GhlTokenStatusSerializer(serializers.Serializer):
    expires_at = serializers.DateTimeField(allow_null=True)
    location_id = serializers.CharField(allow_null=True)
    company_id = serializers.CharField(allow_null=True)
    user_type = serializers.CharField(allow_null=True)
    scope = serializers.CharField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
