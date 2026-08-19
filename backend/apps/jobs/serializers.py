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
    preferred_format = serializers.CharField(max_length=64, required=False)

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
            "thumbnail_path",
            "width",
            "height",
            "duration",
            "clip_start_ms",
            "clip_end_ms",
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
            "thumbnail_path",
            "width",
            "height",
            "duration",
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
    preferred_format = serializers.CharField(max_length=64, required=False, default="best")
    username = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    language_code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    clip_start_ms = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    clip_end_ms = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)

    def validate(self, attrs):
        start = attrs.get("clip_start_ms")
        end = attrs.get("clip_end_ms")
        if (start is None) != (end is None):
            raise serializers.ValidationError(
                "هر دو زمان شروع و پایان برش باید مشخص شوند."
            )
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError(
                "زمان پایان برش باید بعد از زمان شروع باشد."
            )
        return attrs


class ProbeSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)
    telegram_user_id = serializers.IntegerField(required=False, default=0)
