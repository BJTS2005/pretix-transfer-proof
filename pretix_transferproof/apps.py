from django.utils.translation import gettext_lazy as _

from . import __version__

try:
    from pretix.base.plugins import PLUGIN_LEVEL_EVENT, PluginConfig
except ImportError:
    raise RuntimeError("pretix-transfer-proof necesita pretix 2025.7 o superior.") from None


class TransferProofApp(PluginConfig):
    default = True
    name = "pretix_transferproof"
    verbose_name = _("Transferencia con comprobante")
    # 0001 created an integer id; pretix's default is BigAutoField, which made `migrate` warn about
    # unmigrated model changes on every run.
    default_auto_field = "django.db.models.AutoField"

    class PretixPluginMeta:
        name = _("Transferencia con comprobante")
        author = "Bryan Tandayamo"
        version = __version__
        category = "PAYMENT"
        featured = False
        visible = True
        restricted = False
        description = _(
            "Muestra los datos de la cuenta, pide el comprobante (PNG o JPG) y campos adicionales. "
            "El pago queda pendiente hasta que el organizador lo confirme."
        )
        compatibility = "pretix>=2025.7"
        level = PLUGIN_LEVEL_EVENT
        settings_links = [
            ((_("Pagos"), _("Transferencia con comprobante")), "control:event.settings.payment.provider",
             {"provider": "transferproof"}),
        ]
        navigation_links = []

    def ready(self):
        from . import signals  # noqa: F401
