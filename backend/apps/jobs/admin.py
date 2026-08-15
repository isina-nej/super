from django.contrib import admin

from .models import DownloadJob


@admin.register(DownloadJob)
class DownloadJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "source_type",
        "preferred_format",
        "file_size",
        "created_at",
    )
    list_filter = ("status", "source_type", "preferred_format")
    search_fields = ("url", "title", "user__telegram_id", "user__username")
    readonly_fields = ("created_at", "updated_at", "completed_at")
