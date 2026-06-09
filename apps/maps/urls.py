from django.urls import path

from .views import DistanceMatrixView, PolylineView

urlpatterns = [
    path('distance-matrix/', DistanceMatrixView.as_view(), name='maps-distance-matrix'),
    path('polyline/', PolylineView.as_view(), name='maps-polyline'),
]
