import logging

from django.db import transaction
from django.dispatch import receiver
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from pretix.base.logentrytypes import OrderLogEntryType, log_entry_types
from pretix.base.signals import order_placed, register_payment_providers
from pretix.control.signals import html_head as control_html_head
from pretix.presale.signals import (
    global_footer_link, html_head, order_meta_from_request,
)

from . import proofs
from .payment import CHECKOUT_STATE, TransferProofProvider

logger = logging.getLogger(__name__)

# checkout.js switches the payment form to multipart so the image is actually sent
SCRIPT_PAGES = {"event.order.pay", "event.order.pay.change"}


@receiver(register_payment_providers, dispatch_uid="payment_transferproof")
def register_payment_provider(sender, **kwargs):
    return TransferProofProvider


@receiver(html_head, dispatch_uid="transferproof_html_head")
def transferproof_html_head(sender, request=None, **kwargs):
    rm = getattr(request, "resolver_match", None)
    if not rm:
        return ""
    if rm.url_name in SCRIPT_PAGES or (rm.url_name == "event.checkout" and rm.kwargs.get("step") == "payment"):
        return format_html('<script src="{}"></script>', static("pretix_transferproof/checkout.js"))
    return ""


@receiver(control_html_head, dispatch_uid="transferproof_control_html_head")
def transferproof_control_html_head(sender, request=None, **kwargs):
    rm = getattr(request, "resolver_match", None)
    if rm and rm.url_name == "event.settings.payment.provider" and rm.kwargs.get("provider") == "transferproof":
        return format_html('<script src="{}"></script>', static("pretix_transferproof/extra_fields.js"))
    return ""


@receiver(order_meta_from_request, dispatch_uid="transferproof_order_meta")
def transferproof_order_meta(sender, request, **kwargs):
    """Hands the checkout upload/answers over to the order that is about to be created."""
    from pretix.presale.views.cart import cart_session

    cs = cart_session(request)
    if not any(p.get("provider") == TransferProofProvider.identifier for p in cs.get("payments") or []):
        return {}
    state = cs.get(CHECKOUT_STATE) or {}
    if not state.get("cf") and not state.get("answers"):
        return {}
    return {proofs.META_KEY: {"cf": state.get("cf"), "answers": state.get("answers") or []}}


@receiver(order_placed, dispatch_uid="transferproof_order_placed")
def transferproof_order_placed(sender, order, **kwargs):
    """
    Attach the receipt as soon as the order exists, server-side. Before, this only happened when
    the buyer's browser reached the "complete payment" page: closing the tab right after paying
    (e.g. to open the banking app) left the receipt in a temporary file that expired a day later.
    """
    if not proofs.pending_from_meta(order):
        return
    try:
        with transaction.atomic():
            proofs.attach_from_order_meta(order)
    except Exception:
        # Never break order creation; execute_payment retries from the order meta.
        logger.exception("Could not attach transfer receipt to order %s", order.code)


@receiver(global_footer_link, dispatch_uid="transferproof_footer_link")
def transferproof_footer_link(sender, request=None, **kwargs):
    return {
        "label": "Código del plugin de transferencia",
        "url": "https://github.com/BJTS2005/pretix-transfer-proof",
    }


@log_entry_types.new("pretix_transferproof.receipt.uploaded", _("El comprador subió un comprobante de transferencia."))
class ReceiptUploadedLogEntryType(OrderLogEntryType):
    pass
