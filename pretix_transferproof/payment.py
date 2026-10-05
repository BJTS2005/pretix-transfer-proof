import os
from collections import OrderedDict
from io import BytesIO

from django import forms
from django.core.files.base import ContentFile
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.translation import gettext, gettext_lazy as _
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from pretix.base.models import OrderPayment
from pretix.base.payment import BasePaymentProvider, PaymentException

from .models import TransferProof

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_PIXELS = 10_000 * 10_000


class ReceiptField(forms.FileField):
    def clean(self, data, initial=None):
        data = super().clean(data, initial)
        if not data:
            return data
        return validate_and_reencode(data)


def validate_and_reencode(uploaded):
    name = uploaded.name or "receipt.jpg"
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise forms.ValidationError(_("Solo se permiten archivos PNG, JPG o JPEG."))

    from django.conf import settings
    limit = getattr(settings, "FILE_UPLOAD_MAX_SIZE_OTHER", 10 * 1024 * 1024)
    if uploaded.size > limit:
        raise forms.ValidationError(_("El archivo supera el tamaño máximo permitido."))

    try:
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        raw = BytesIO(uploaded.read())
        image = Image.open(raw)
        image.load()
    except DecompressionBombError:
        raise forms.ValidationError(_("La imagen tiene demasiados píxeles."))
    except (UnidentifiedImageError, OSError, ValueError):
        raise forms.ValidationError(_("El archivo no es una imagen PNG o JPEG válida."))

    if image.format not in ("PNG", "JPEG"):
        raise forms.ValidationError(_("Solo se permiten imágenes PNG o JPEG."))
    if image.width * image.height > MAX_PIXELS:
        raise forms.ValidationError(_("La imagen tiene demasiados píxeles."))

    out = BytesIO()
    if image.format == "JPEG" or ext in (".jpg", ".jpeg"):
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(out, format="JPEG", quality=85)
        filename = "receipt.jpg"
    else:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        image.save(out, format="PNG")
        filename = "receipt.png"
    out.seek(0)
    return ContentFile(out.read(), name=filename)


class TransferProofProvider(BasePaymentProvider):
    identifier = "transferproof"
    verbose_name = _("Transferencia con comprobante")
    abort_pending_allowed = True
    execute_payment_needs_user = True

    @property
    def public_name(self):
        return str(self.settings.get("public_name") or self.verbose_name)

    @property
    def settings_form_fields(self):
        base = super().settings_form_fields
        return OrderedDict(
            [
                ("_enabled", base["_enabled"]),
                (
                    "bank_details",
                    forms.CharField(
                        label=_("Datos de la cuenta"),
                        widget=forms.Textarea(attrs={"rows": 6}),
                        help_text=_("Banco, tipo de cuenta, número, titular, cédula. Se muestra al comprador."),
                        required=True,
                    ),
                ),
                (
                    "public_name",
                    forms.CharField(
                        label=_("Nombre visible"),
                        required=False,
                        help_text=_("Si lo dejas vacío, se muestra “Transferencia con comprobante”."),
                    ),
                ),
                (
                    "receipt_required",
                    forms.BooleanField(
                        label=_("Comprobante obligatorio"),
                        required=False,
                        help_text=_(
                            "Si está activo, no se puede continuar sin imagen. "
                            "Desactívalo para reservas en las que algunos pagan después."
                        ),
                    ),
                ),
            ]
        )

    @property
    def test_mode_message(self):
        return _("En modo prueba el pago sigue pendiente hasta que lo marques pagado en el backend.")

    def payment_form_fields(self):
        required = self.settings.get("receipt_required", as_type=bool)
        return OrderedDict(
            [
                (
                    "receipt",
                    ReceiptField(
                        label=_("Comprobante de transferencia"),
                        required=required,
                        help_text=_("Solo PNG, JPG o JPEG."),
                    ),
                )
            ]
        )

    def payment_form(self, request):
        selected = request.method == "POST" and request.POST.get("payment") == self.identifier
        form = self.payment_form_class(
            data=request.POST if selected else None,
            files=request.FILES if selected else None,
            prefix="payment_%s" % self.identifier,
        )
        form.fields = self.payment_form_fields()
        for field in form.fields.values():
            field._required = field.required
            field.required = False
            field.widget.is_required = False
        return form

    def _store_upload(self, request, uploaded, previous_id=None):
        from datetime import timedelta

        from django.utils.timezone import now

        from pretix.base.models import CachedFile

        if previous_id:
            old = CachedFile.objects.filter(id=previous_id).first()
            if old:
                old.delete()

        cf = CachedFile(
            expires=now() + timedelta(days=1),
            date=now(),
            web_download=False,
            filename=uploaded.name,
            type="image/jpeg" if uploaded.name.endswith(".jpg") else "image/png",
        )
        cf.save()
        cf.bind_to_session(request)
        cf.file.save(uploaded.name, uploaded)
        cf.save()
        return str(cf.id)

    def checkout_prepare(self, request, cart):
        from pretix.presale.views.cart import cart_session

        form = self.payment_form(request)
        if not form.is_valid():
            return False
        uploaded = form.cleaned_data.get("receipt")
        cs = cart_session(request)
        if not uploaded:
            if self.settings.get("receipt_required", as_type=bool):
                form.add_error("receipt", _("Sube el comprobante para continuar."))
                return False
            cs.pop("transferproof_cf", None)
            return True
        cs["transferproof_cf"] = self._store_upload(request, uploaded, cs.get("transferproof_cf"))
        request.session["transferproof_pending_%s" % self.event.pk] = cs["transferproof_cf"]
        return True

    def payment_prepare(self, request, payment):
        form = self.payment_form(request)
        if not form.is_valid():
            return False
        uploaded = form.cleaned_data.get("receipt")
        if not uploaded:
            if self.settings.get("receipt_required", as_type=bool) and not TransferProof.objects.filter(payment__order=payment.order, payment__state__in=["created", "pending", "confirmed"]).exists():
                form.add_error("receipt", _("Sube el comprobante para continuar."))
                return False
            return True
        request.session["transferproof_change_%s" % payment.order_id] = self._store_upload(
            request,
            uploaded,
            request.session.get("transferproof_change_%s" % payment.order_id),
        )
        return True

    def payment_is_valid_session(self, request, payment=None):
        if not self.settings.get("receipt_required", as_type=bool):
            return True
        if payment and TransferProof.objects.filter(payment=payment).exists():
            return True
        if request.session.get("transferproof_pending_%s" % self.event.pk):
            return True
        if payment and request.session.get("transferproof_change_%s" % payment.order_id):
            return True
        from pretix.presale.views.cart import cart_session

        return bool(cart_session(request).get("transferproof_cf"))

    def execute_payment(self, request, payment):
        if TransferProof.objects.filter(payment=payment).exists():
            return None

        cf_id = None
        source = None
        if request is not None:
            cf_id = request.session.get("transferproof_change_%s" % payment.order_id)
            source = "change"
        if not cf_id:
            cf_id = (payment.order.meta_info_data or {}).get("transferproof_cf")
            source = "meta"
        if not cf_id:
            if self.settings.get("receipt_required", as_type=bool):
                raise PaymentException(_("Falta el comprobante de transferencia."))
            return None

        from pretix.base.models import CachedFile

        cf = CachedFile.objects.filter(id=cf_id).first()
        if not cf or not cf.file:
            if self.settings.get("receipt_required", as_type=bool):
                raise PaymentException(_("El comprobante ya no está disponible. Súbelo de nuevo."))
            return None
        if request is not None and not cf.allowed_for_session(request):
            raise PaymentException(_("El comprobante no corresponde a esta sesión."))

        proof = TransferProof(payment=payment, original_name=cf.filename or "receipt.jpg")
        proof.file.save(cf.filename or "receipt.jpg", cf.file, save=False)
        proof.save()
        cf.delete()

        if source == "meta":
            meta = payment.order.meta_info_data or {}
            meta.pop("transferproof_cf", None)
            meta.pop("transferproof_cart", None)
            payment.order.meta_info = __import__("json").dumps(meta)
            payment.order.save(update_fields=["meta_info"])
        if request is not None:
            request.session.pop("transferproof_change_%s" % payment.order_id, None)
            request.session.pop("transferproof_pending_%s" % self.event.pk, None)
        return None

    def _bank_details(self):
        return self.settings.get("bank_details") or ""

    def payment_form_render(self, request, total=None, order=None) -> str:
        template = get_template("pretix_transferproof/checkout_payment_form.html")
        form = self.payment_form(request)
        return template.render(
            {
                "event": self.event,
                "details": self._bank_details(),
                "form": form,
                "required": self.settings.get("receipt_required", as_type=bool),
            },
            request=request,
        )

    def checkout_confirm_render(self, request, order=None, info_data=None) -> str:
        from pretix.presale.views.cart import cart_session

        has_file = bool(cart_session(request).get("transferproof_cf"))
        has_file = has_file or bool(request.session.get("transferproof_pending_%s" % self.event.pk))
        if order is not None:
            has_file = has_file or bool(request.session.get("transferproof_change_%s" % order.pk))
            has_file = has_file or TransferProof.objects.filter(payment__order=order).exists()
        template = get_template("pretix_transferproof/checkout_confirm.html")
        return template.render(
            {"event": self.event, "details": self._bank_details(), "has_file": has_file},
            request=request,
        )

    def payment_pending_render(self, request, payment) -> str:
        template = get_template("pretix_transferproof/pending.html")
        proof = TransferProof.objects.filter(payment=payment).first()
        return template.render(
            {
                "event": self.event,
                "order": payment.order,
                "amount": payment.amount,
                "details": self._bank_details(),
                "proof": proof,
            },
            request=request,
        )

    def payment_control_render(self, request, payment) -> str:
        template = get_template("pretix_transferproof/control.html")
        proof = TransferProof.objects.filter(payment=payment).first()
        return template.render(
            {"request": request, "event": self.event, "order": payment.order, "proof": proof},
            request=request,
        )

    def payment_control_render_short(self, payment) -> str:
        if TransferProof.objects.filter(payment=payment).exists():
            return gettext("Comprobante adjunto")
        return gettext("Sin comprobante")

    def shred_payment_info(self, obj):
        if isinstance(obj, OrderPayment):
            proof = TransferProof.objects.filter(payment=obj).first()
            if proof:
                if proof.file:
                    proof.file.delete(save=False)
                proof.delete()
        super().shred_payment_info(obj)
