import django.db.models.deletion
from django.db import migrations, models

import pretix_transferproof.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        # OrderPayment was created in this migration (pretix 2.0, 2018). Depending on a much newer
        # pretix migration (0306, only in pretix >= 2026.7) made `migrate` fail on older installs.
        ("pretixbase", "0096_auto_20180722_0801"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransferProof",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(max_length=255, upload_to=pretix_transferproof.models.proof_path)),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transferproof",
                        to="pretixbase.orderpayment",
                    ),
                ),
            ],
        ),
    ]
