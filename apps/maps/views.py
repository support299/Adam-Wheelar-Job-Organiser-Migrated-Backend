"""Server-side proxies for the Google Routes API.

The API key is never sent to the browser — all requests go through here.
Logic ported directly from route-polyline.functions.ts and routes-matrix.functions.ts.
"""

import logging

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import DistanceMatrixInputSerializer, PolylineInputSerializer

logger = logging.getLogger(__name__)

ROUTES_BASE = 'https://routes.googleapis.com'


def _waypoint(p: dict) -> dict:
    return {'waypoint': {'location': {'latLng': {'latitude': p['lat'], 'longitude': p['lng']}}}}


def _wp(p: dict) -> dict:
    return {'location': {'latLng': {'latitude': p['lat'], 'longitude': p['lng']}}}


class DistanceMatrixView(APIView):
    """Compute an N×N road distance/duration matrix via Google Routes API.

    Returns flat arrays (row-major order). Unreachable pairs are encoded as -1.
    """

    def post(self, request):
        serializer = DistanceMatrixInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        points = serializer.validated_data['points']
        n = len(points)

        distance = [0] * (n * n)
        duration = [0] * (n * n)

        if n <= 1:
            return Response({'n': n, 'distance': distance, 'duration': duration})

        api_key = settings.GOOGLE_MAPS_SERVER_API_KEY
        if not api_key:
            return Response(
                {'detail': 'GOOGLE_MAPS_SERVER_API_KEY is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        TILE = 25
        for i0 in range(0, n, TILE):
            for j0 in range(0, n, TILE):
                origins = [_waypoint(p) for p in points[i0:i0 + TILE]]
                destinations = [_waypoint(p) for p in points[j0:j0 + TILE]]
                try:
                    resp = requests.post(
                        f'{ROUTES_BASE}/distanceMatrix/v2:computeRouteMatrix',
                        json={
                            'origins': origins,
                            'destinations': destinations,
                            'travelMode': 'DRIVE',
                            'routingPreference': 'TRAFFIC_AWARE',
                        },
                        headers={
                            'X-Goog-Api-Key': api_key,
                            'X-Goog-FieldMask': (
                                'originIndex,destinationIndex,'
                                'duration,distanceMeters,status,condition'
                            ),
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                except requests.RequestException as exc:
                    logger.error('Routes matrix API error: %s', exc)
                    return Response(
                        {'detail': f'Routes API error: {exc}'},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

                for el in resp.json():
                    i = i0 + el.get('originIndex', 0)
                    j = j0 + el.get('destinationIndex', 0)
                    ok = (
                        el.get('condition') == 'ROUTE_EXISTS'
                        and (not el.get('status', {}).get('code'))
                    )
                    if ok and el.get('distanceMeters') is not None and el.get('duration'):
                        distance[i * n + j] = el['distanceMeters']
                        duration[i * n + j] = int(
                            el['duration'].rstrip('s') or 0
                        )
                    else:
                        distance[i * n + j] = -1
                        duration[i * n + j] = -1

        return Response({'n': n, 'distance': distance, 'duration': duration})


class PolylineView(APIView):
    """Fetch a road-snapped encoded polyline for an ordered set of points."""

    def post(self, request):
        serializer = PolylineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        points = serializer.validated_data['points']

        api_key = settings.GOOGLE_MAPS_SERVER_API_KEY
        if not api_key:
            return Response(
                {'detail': 'GOOGLE_MAPS_SERVER_API_KEY is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        origin = _wp(points[0])
        destination = _wp(points[-1])
        intermediates = [_wp(p) for p in points[1:-1]]

        payload = {
            'origin': origin,
            'destination': destination,
            'travelMode': 'DRIVE',
            'routingPreference': 'TRAFFIC_AWARE',
            'polylineEncoding': 'ENCODED_POLYLINE',
        }
        if intermediates:
            payload['intermediates'] = intermediates

        try:
            resp = requests.post(
                f'{ROUTES_BASE}/directions/v2:computeRoutes',
                json=payload,
                headers={
                    'X-Goog-Api-Key': api_key,
                    'X-Goog-FieldMask': (
                        'routes.polyline.encodedPolyline,'
                        'routes.distanceMeters,routes.duration'
                    ),
                },
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error('Routes polyline API error: %s', exc)
            return Response(
                {'detail': f'Routes API error: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = resp.json()
        route = (data.get('routes') or [{}])[0]
        return Response({
            'encodedPolyline': route.get('polyline', {}).get('encodedPolyline', ''),
            'distanceMeters': route.get('distanceMeters', 0),
            'durationSeconds': int((route.get('duration') or '0s').rstrip('s') or 0),
        })
