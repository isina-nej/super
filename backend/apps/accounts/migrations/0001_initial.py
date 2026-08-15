# Generated manually for greenfield bootstrap

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TelegramUser",
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
                ("telegram_id", models.BigIntegerField(db_index=True, unique=True)),
                ("username", models.CharField(blank=True, default="", max_length=255)),
                (
                    "first_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "last_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "language_code",
                    models.CharField(blank=True, default="", max_length=16),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
