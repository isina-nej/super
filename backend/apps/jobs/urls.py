from django.urls import path

from apps.jobs.views import HealthView, JobAckView, JobDetailView, JobListCreateView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("jobs/", JobListCreateView.as_view(), name="job-list-create"),
    path("jobs/<int:job_id>/", JobDetailView.as_view(), name="job-detail"),
    path("jobs/<int:job_id>/ack/", JobAckView.as_view(), name="job-ack"),
]
