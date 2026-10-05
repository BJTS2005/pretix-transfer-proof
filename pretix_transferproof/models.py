import os
import string

from django.db import models
from django.utils.crypto import get_random_string


def proof_path(instance, filename):
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

    class Meta:
        app_label = "pretix_transferproof"
