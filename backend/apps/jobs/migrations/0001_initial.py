# Generated manually for greenfield bootstrap

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DownloadJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("url", models.URLField(max_length=2048)),
                ("chat_id", models.BigIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("downloading", "Downloading"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                            ("acked", "Acked"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=32,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("ytdlp", "yt-dlp"),
                            ("direct", "Direct HTTP"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                (
                    "preferred_format",
                    models.CharField(
                        choices=[
                            ("best", "Best quality"),
                            ("audio", "Audio only"),
                        ],
                        default="best",
                        max_length=16,
                    ),
                ),
                ("file_path", models.CharField(blank=True, default="", max_length=1024)),
                ("file_size", models.BigIntegerField(blank=True, null=True)),
                ("mime_type", models.CharField(blank=True, default="", max_length=255)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("error", models.TextField(blank=True, default="")),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="accounts.telegramuser",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="downloadjob",
            index=models.Index(
                fields=["status", "created_at"],
                name="jobs_downlo_status_6f3c1a_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="downloadjob",
            index=models.Index(
                fields=["user", "status"],
                name="jobs_downlo_user_id_status_idx",
            ),
        ),
    ]
