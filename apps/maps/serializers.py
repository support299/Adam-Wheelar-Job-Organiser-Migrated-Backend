from rest_framework import serializers


class LatLngSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class DistanceMatrixInputSerializer(serializers.Serializer):
    points = LatLngSerializer(many=True, min_length=1, max_length=50)


class PolylineInputSerializer(serializers.Serializer):
    points = LatLngSerializer(many=True, min_length=2, max_length=25)
