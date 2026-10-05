from django.utils.translation import gettext_lazy as _

from pretix.base.plugins import PLUGIN_LEVEL_EVENT, PluginConfig


class TransferProofApp(PluginConfig):
    name = "pretix_transferproof"
    verbose_name = _("Transferencia con comprobante")

    class PretixPluginMeta:
        name = _("Transferencia con comprobante")
        author = "Bryan Tandayamo"
        version = "1.0.0"
        category = "PAYMENT"
        featured = False
        visible = True
        restricted = False
        description = _(
            "Muestra los datos de la cuenta y permite subir un comprobante "
            "PNG, JPG o JPEG. El pago queda pendiente hasta que el organizador lo confirme."
        )
        compatibility = "pretix>=2024.7"
        level = PLUGIN_LEVEL_EVENT
        settings_links = []
        navigation_links = []

    def ready(self):
        from . import signals  # noqa: F401
