from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="downloadjob",
            name="celery_task_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="downloadjob",
            name="preferred_format",
            field=models.CharField(default="best", max_length=64),
        ),
        migrations.AlterField(
            model_name="downloadjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("downloading", "Downloading"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                    ("expired", "Expired"),
                    ("acked", "Acked"),
                    ("canceled", "Canceled"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
            ),
        ),
    ]
