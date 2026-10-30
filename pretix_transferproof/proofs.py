"""Storing receipts and answers on a payment, and reading them back."""
import json
import logging
import os
from datetime import timedelta

from django.core.files import File
from django.db import transaction
from django.utils.timezone import now

from .models import TransferProof

logger = logging.getLogger(__name__)

ANSWERS_KEY = "transferproof_answers"
META_KEY = "transferproof"


# ----------------------------------------------------------------------------- uploads (before a payment exists)
def store_upload(request, content):
    """Keeps the validated image as a temporary CachedFile bound to the buyer's session."""
    from pretix.base.models import CachedFile

    cf = CachedFile(
        expires=now() + timedelta(days=2),
        date=now(),
        web_download=False,
        filename=content.name,
        type="image/png" if content.name.endswith(".png") else "image/jpeg",
    )
    bind = getattr(cf, "bind_to_session", None)  # only exists in pretix >= 2026.x
    if bind:
        try:
            bind(request)
        except ValueError:  # no session key yet; the id only ever lives in this session anyway
            pass
    cf.save()
    cf.file.save(content.name, content)
    return str(cf.id)


def cached_file(cf_id):
    from pretix.base.models import CachedFile

    if not cf_id:
        return None
    cf = CachedFile.objects.filter(id=cf_id).first()
    return cf if cf and cf.file else None


def discard_upload(cf_id):
    from pretix.base.models import CachedFile

    if cf_id:
        CachedFile.objects.filter(id=cf_id).delete()


# ----------------------------------------------------------------------------- reading
def proof_of(payment):
    # Query instead of payment.transferproof: Django caches a missing reverse one-to-one as None,
    # which goes stale once the receipt is attached through another instance of the payment.
    return TransferProof.objects.filter(payment_id=payment.pk).first()


def answers_of(payment):
    answers = (payment.info_data or {}).get(ANSWERS_KEY)
    if isinstance(answers, list):
        return answers
    proof = proof_of(payment)
    if proof and proof.extra_answers:  # receipts stored by v1 of the plugin
        return [{"label": k, "value": v} for k, v in proof.extra_answers.items()]
    return []


def latest_proof_of_order(order):
    return TransferProof.objects.filter(payment__order=order).select_related("payment").order_by("-created").first()


# ----------------------------------------------------------------------------- writing
def attach(payment, *, answers=None, cf=None, copy_from=None):
    """
    Saves answers and/or a receipt on ``payment``. ``cf`` is a CachedFile with a new upload,
    ``copy_from`` an existing TransferProof (e.g. of the payment this one replaces).
    A new receipt replaces the previous one of the same payment.
    """
    with transaction.atomic():
        if answers is not None:
            info = payment.info_data or {}
            info[ANSWERS_KEY] = answers
            payment.info_data = info
            payment.save(update_fields=["info"])

        source = cf.file if cf else (copy_from.file if copy_from and copy_from.payment_id != payment.pk else None)
        if not source:
            return proof_of(payment)

        name = cf.filename if cf else os.path.basename(copy_from.file.name)
        proof = proof_of(payment) or TransferProof(payment=payment)
        old_file = proof.file.name if proof.pk and proof.file else None
        proof.original_name = (cf.filename if cf else copy_from.original_name) or name
        proof.extra_answers = {}
        source.open("rb")
        try:
            proof.file.save(name, File(source), save=False)
        finally:
            source.close()
        proof.created = now()
        proof.save()

        if old_file and old_file != proof.file.name:
            storage = proof.file.storage
            transaction.on_commit(lambda: storage.delete(old_file))
        if cf:
            cf_id = cf.id
            transaction.on_commit(lambda: discard_upload(cf_id))
        payment.order.log_action(
            "pretix_transferproof.receipt.uploaded",
            data={"payment": payment.pk, "local_id": payment.local_id},
        )
        return proof


LEGACY_META_KEYS = ("transferproof_cf", "transferproof_cart")  # written by v1


def pending_from_meta(order):
    """Upload/answers from checkout that are not attached to the payment yet (or None)."""
    meta = order.meta_info_data or {}
    data = meta.get(META_KEY)
    if isinstance(data, dict):
        return data
    if meta.get("transferproof_cf"):
        return {"cf": meta["transferproof_cf"], "answers": []}
    return None


def attach_from_order_meta(order):
    """Moves the checkout upload/answers (kept in the order meta) onto the order's payment."""
    data = pending_from_meta(order)
    if data is None:
        return False
    payment = order.payments.filter(provider="transferproof").order_by("-pk").first()
    if not payment:
        return False
    attach(payment, answers=data.get("answers") or [], cf=cached_file(data.get("cf")))
    meta = dict(order.meta_info_data or {})
    for key in (META_KEY,) + LEGACY_META_KEYS:
        meta.pop(key, None)
    order.meta_info = json.dumps(meta)
    order.save(update_fields=["meta_info"])
    order.__dict__.pop("meta_info_data", None)  # it is a cached_property
    return True
