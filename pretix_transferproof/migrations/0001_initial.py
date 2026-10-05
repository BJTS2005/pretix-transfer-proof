from django.db import migrations, models
import django.db.models.deletion
import pretix_transferproof.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("pretixbase", "0311_fix_unshredded_invoices"),
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
