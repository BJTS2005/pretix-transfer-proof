from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pretix_transferproof", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferproof",
            name="extra_answers",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
