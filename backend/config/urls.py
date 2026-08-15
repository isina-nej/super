from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.jobs.urls")),
]


def server_error(request, *args, **kwargs):
    return JsonResponse({"detail": "خطای داخلی سرور"}, status=500)


handler500 = "config.urls.server_error"
