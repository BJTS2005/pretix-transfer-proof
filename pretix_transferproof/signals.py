from django.dispatch import receiver
from django.templatetags.static import static

from pretix.base.signals import register_payment_providers
from pretix.presale.signals import global_footer_link, html_head, order_meta_from_request

from .payment import TransferProofProvider


@receiver(register_payment_providers, dispatch_uid="payment_transferproof")
def register_payment_provider(sender, **kwargs):
    return TransferProofProvider


@receiver(html_head, dispatch_uid="transferproof_html_head")
def transferproof_html_head(sender, request=None, **kwargs):
    return '<script src="%s"></script>' % static("pretix_transferproof/checkout.js")


@receiver(order_meta_from_request, dispatch_uid="transferproof_order_meta")
def transferproof_order_meta(sender, request, **kwargs):
    from pretix.presale.views.cart import cart_session, get_or_create_cart_id

    cs = cart_session(request)
    payments = cs.get("payments") or []
    if not any(p.get("provider") == TransferProofProvider.identifier for p in payments):
        return {}
    cf_id = cs.get("transferproof_cf")
    if not cf_id:
        return {}
    return {
        "transferproof_cf": cf_id,
        "transferproof_cart": get_or_create_cart_id(request, create=False),
    }


@receiver(global_footer_link, dispatch_uid="transferproof_footer_link")
def transferproof_footer_link(sender, request=None, **kwargs):
    return {
        "label": "Código del plugin de transferencia",
        "url": "https://github.com/BJTS2005/pretix-transfer-proof",
    }
