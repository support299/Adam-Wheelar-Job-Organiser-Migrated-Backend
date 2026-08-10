from django.urls import path

from .views import DashboardView, StaffReportSummaryView, StaffReportView

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('staff-report/', StaffReportView.as_view(), name='staff-report'),
    path('staff-report/summary/', StaffReportSummaryView.as_view(), name='staff-report-summary'),
]
