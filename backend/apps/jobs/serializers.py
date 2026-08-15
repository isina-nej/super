from rest_framework import serializers

from apps.accounts.models import TelegramUser
from apps.jobs.models import DownloadJob


class TelegramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramUser
        fields = (
            "id",
            "telegram_id",
            "username",
            "first_name",
            "last_name",
            "language_code",
            "is_active",
            "created_at",
        )
        read_only_fields = fields


class DownloadJobSerializer(serializers.ModelSerializer):
    telegram_user_id = serializers.IntegerField(source="user.telegram_id", read_only=True)

    class Meta:
        model = DownloadJob
        fields = (
            "id",
            "telegram_user_id",
            "url",
            "chat_id",
            "status",
            "source_type",
            "preferred_format",
            "file_path",
            "file_size",
            "mime_type",
            "title",
            "error",
            "progress",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = (
            "id",
            "telegram_user_id",
            "status",
            "source_type",
            "file_path",
            "file_size",
            "mime_type",
            "title",
            "error",
            "progress",
            "created_at",
            "updated_at",
            "completed_at",
        )


class CreateJobSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)
    telegram_user_id = serializers.IntegerField()
    chat_id = serializers.IntegerField()
    preferred_format = serializers.ChoiceField(
        choices=DownloadJob.PreferredFormat.choices,
        default=DownloadJob.PreferredFormat.BEST,
        required=False,
    )
    username = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    language_code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
