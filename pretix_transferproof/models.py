import os
import string

from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.crypto import get_random_string


def proof_path(instance, filename):
    # "cachedfiles/" is never served directly by pretix's web server config, like pretix's own answer files.
    secret = get_random_string(32, allowed_chars=string.ascii_letters + string.digits)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        ext = ".jpg"
    event = instance.payment.order.event
    return "cachedfiles/transferproof/{org}/{ev}/{secret}{ext}".format(
        org=event.organizer.slug,
        ev=event.slug,
        secret=secret,
        ext=ext,
    )


class TransferProof(models.Model):
    payment = models.OneToOneField(
        "pretixbase.OrderPayment",
        related_name="transferproof",
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to=proof_path, max_length=255)
    original_name = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    # Legacy (v1): answers now live in OrderPayment.info_data["transferproof_answers"]
    extra_answers = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "pretix_transferproof"


@receiver(post_delete, sender=TransferProof, dispatch_uid="transferproof_delete_file")
def delete_proof_file(sender, instance, **kwargs):
    """Receipts contain bank data: never leave the image behind when the row goes away."""
    if instance.file:
        storage, name = instance.file.storage, instance.file.name
        transaction.on_commit(lambda: storage.delete(name))
