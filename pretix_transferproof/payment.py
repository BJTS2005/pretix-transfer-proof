from collections import OrderedDict

from django import forms
from django.contrib import messages
from django.template.loader import get_template
from django.utils.translation import gettext, gettext_lazy as _

from pretix.base.models import OrderPayment
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.templatetags.money import money_filter
from pretix.multidomain.urlreverse import eventreverse

from . import extra_fields, proofs
from .images import validate_and_reencode

CHECKOUT_STATE = "transferproof"  # key inside the cart session
ORDER_FLOW_URLS = ("event.order.pay", "event.order.pay.confirm", "event.order.pay.complete")


def payment_state_key(payment):
    return "transferproof_payment_%s" % payment.pk


class ReceiptField(forms.FileField):
    widget = forms.FileInput(attrs={"accept": "image/png,image/jpeg"})

    def clean(self, data, initial=None):
        data = super().clean(data, initial)
        if not data:
            return data
        return validate_and_reencode(data)


class TransferProofProvider(BasePaymentProvider):
    identifier = "transferproof"
    verbose_name = _("Transferencia con comprobante")
    abort_pending_allowed = True
    execute_payment_needs_user = True

    # ------------------------------------------------------------------ settings
    @property
    def public_name(self):
        return str(self.settings.get("public_name") or self.verbose_name)

    @property
    def settings_form_fields(self):
        # Keep pretix's standard options (fees, availability dates, min/max total, countries,
        # sales channels, invoice text...) and add ours right after "enabled".
        base = OrderedDict(super().settings_form_fields)
        own = [
            ("bank_details", forms.CharField(
                label=_("Datos de la cuenta"),
                widget=forms.Textarea(attrs={"rows": 6}),
                help_text=_("Banco, tipo de cuenta, número, titular, cédula/RUC. Se muestra al comprador y va en su correo."),
                required=True,
            )),
            ("public_name", forms.CharField(
                label=_("Nombre visible"),
                required=False,
                help_text=_("Si lo dejas vacío, se muestra «Transferencia con comprobante»."),
            )),
            ("receipt_required", forms.BooleanField(
                label=_("Comprobante obligatorio"),
                required=False,
                help_text=_("Si está activo, no se puede terminar la compra sin imagen. Desactívalo si "
                            "algunos compradores transfieren después."),
            )),
            ("extra_fields", forms.CharField(
                label=_("Campos adicionales"),
                required=False,
                widget=forms.Textarea(attrs={"rows": 8, "class": "extra-fields-json"}),
                help_text=_('Lista JSON. Ejemplo: [{"label": "Número de referencia", "type": "text", "required": true}, '
                            '{"label": "Banco de origen", "type": "choice", "options": ["Pichincha", "Guayaquil"]}]'),
            )),
        ]
        fields = OrderedDict([("_enabled", base.pop("_enabled"))] + own + list(base.items()))
        return fields

    def settings_form_clean(self, cleaned_data):
        key = "payment_%s_extra_fields" % self.identifier
        try:
            cleaned_data[key] = extra_fields.clean(cleaned_data.get(key))
        except forms.ValidationError as e:
            raise forms.ValidationError({key: e.messages}) from None
        return cleaned_data

    @property
    def test_mode_message(self):
        return _("En modo de prueba el pago queda pendiente hasta que lo marques como pagado.")

    @property
    def receipt_required(self):
        return bool(self.settings.get("receipt_required", as_type=bool))

    @property
    def fields(self):
        return extra_fields.parse(self.settings.get("extra_fields") or "[]")

    def _bank_details(self):
        return self.settings.get("bank_details") or ""

    # ------------------------------------------------------------------ where are we?
    def _order_flow_payment(self, request):
        """The OrderPayment when we are on /order/.../pay/<payment>/..., else None."""
        rm = getattr(request, "resolver_match", None)
        if not rm or rm.url_name not in ORDER_FLOW_URLS or "payment" not in rm.kwargs:
            return None
        cache = request.__dict__.setdefault("_transferproof_payments", {})
        key = (rm.kwargs.get("order"), rm.kwargs.get("payment"))
        if key not in cache:
            cache[key] = OrderPayment.objects.filter(
                pk=rm.kwargs["payment"], order__code=rm.kwargs.get("order"), order__event=self.event,
            ).select_related("order").first()
        return cache[key]

    def _checkout_state(self, request):
        from pretix.presale.views.cart import cart_session

        cs = cart_session(request)
        if not isinstance(cs.get(CHECKOUT_STATE), dict):
            cs[CHECKOUT_STATE] = {}
        return cs[CHECKOUT_STATE]

    # ------------------------------------------------------------------ form
    @property
    def payment_form_fields(self):
        fields = OrderedDict([
            ("receipt", ReceiptField(
                label=_("Comprobante de transferencia"),
                required=self.receipt_required,
                help_text=_("Imagen PNG o JPG (captura o foto)."),
            )),
        ])
        fields.update(extra_fields.form_fields(self.fields))
        return fields

    def _order_answers(self, order):
        for p in order.payments.filter(provider=self.identifier).order_by("-pk"):
            answers = proofs.answers_of(p)
            if answers:
                return answers
        return []

    def _stored_answers(self, request, order=None):
        """Answers to pre-fill: what the buyer already typed, so nothing has to be entered twice."""
        payment = self._order_flow_payment(request)
        if payment is not None:  # retrying an existing payment
            state = request.session.get(payment_state_key(payment)) or {}
            return state.get("answers") or proofs.answers_of(payment) or self._order_answers(payment.order)
        if order is not None:  # "change payment method" page
            return self._order_answers(order)
        return self._checkout_state(request).get("answers") or []

    def payment_form(self, request, order=None):
        # The same request renders the form and then validates it (checkout_prepare/payment_prepare):
        # build it once so the image is decoded and re-encoded only once.
        cache = request.__dict__.setdefault("_transferproof_forms", {})
        if self.identifier in cache:
            return cache[self.identifier]
        selected = request.method == "POST" and request.POST.get("payment") == self.identifier
        form = self.payment_form_class(
            data=request.POST if selected else None,
            files=request.FILES if selected else None,
            prefix="payment_%s" % self.identifier,
            initial=extra_fields.initial_from(self.fields, self._stored_answers(request, order)),
        )
        form.fields = self.payment_form_fields
        for field in form.fields.values():
            field._required = field.required
            field.required = False
            field.widget.is_required = False
        form.current_receipt = self._current_receipt(request, order)
        if form.current_receipt:
            form.fields["receipt"]._required = False  # already sent; a new file only replaces it
        cache[self.identifier] = form
        return form

    def _file_not_sent(self, request):
        name = "payment_%s-receipt" % self.identifier
        return bool(request.POST.get(name)) and name not in request.FILES

    def _current_receipt(self, request, order=None):
        """The receipt the buyer already sent, to show it instead of asking again (None if none)."""
        payment = self._order_flow_payment(request)
        if payment is None and order is None:  # checkout
            cf = proofs.cached_file(self._checkout_state(request).get("cf"))
            return {"name": cf.filename} if cf else None
        if payment is not None:
            state = request.session.get(payment_state_key(payment)) or {}
            cf = proofs.cached_file(state.get("cf"))
            if cf:
                return {"name": cf.filename}
            proof = proofs.proof_of(payment) or proofs.latest_proof_of_order(payment.order)
        else:
            proof = proofs.latest_proof_of_order(order)
        if not proof:
            return None
        return {"name": proof.original_name or "comprobante", "url": self.proof_url(proof.payment)}

    def payment_form_render(self, request, total=None, order=None) -> str:
        template = get_template("pretix_transferproof/checkout_payment_form.html")
        form = self.payment_form(request, order)
        return template.render({
            "event": self.event,
            "details": self._bank_details(),
            "form": form,
            "required": self.receipt_required,
            "current": form.current_receipt,
        }, request=request)

    # ------------------------------------------------------------------ checkout (new order)
    def checkout_prepare(self, request, cart):
        form = self.payment_form(request)
        if self._file_not_sent(request):
            messages.error(request, _("Tu navegador no envió la imagen. Recarga la página e inténtalo de nuevo."))
            return False
        if not form.is_valid():
            return False
        state = self._checkout_state(request)
        new_file = form.cleaned_data.get("receipt")
        if new_file:
            proofs.discard_upload(state.get("cf"))
            state["cf"] = proofs.store_upload(request, new_file)
        elif state.get("cf") and not proofs.cached_file(state["cf"]):
            state.pop("cf")  # expired
        if self.receipt_required and not state.get("cf"):
            form.add_error("receipt", _("Sube el comprobante para continuar."))
            messages.error(request, _("Sube el comprobante para continuar."))
            return False
        state["answers"] = extra_fields.answers_from(self.fields, form.cleaned_data)
        return True

    def payment_is_valid_session(self, request):
        payment = self._order_flow_payment(request)
        if payment is not None:
            state = request.session.get(payment_state_key(payment))
            if state is not None:
                answers = state.get("answers") or []
                has_file = bool(proofs.cached_file(state.get("cf")) or state.get("copy_from"))
            else:  # e.g. right after checkout: everything already sits on the payment (or the order meta)
                pending = proofs.pending_from_meta(payment.order) or {}
                answers = proofs.answers_of(payment) or pending.get("answers") or []
                has_file = bool(proofs.proof_of(payment) or proofs.cached_file(pending.get("cf")))
        else:
            state = self._checkout_state(request)
            answers, has_file = state.get("answers") or [], bool(proofs.cached_file(state.get("cf")))
        if self.receipt_required and not has_file:
            return False
        return not extra_fields.missing_required(self.fields, answers)

    def checkout_confirm_render(self, request, order=None, info_data=None) -> str:
        payment = self._order_flow_payment(request)
        if payment is not None:
            state = request.session.get(payment_state_key(payment)) or {}
            answers = state.get("answers", proofs.answers_of(payment))
            receipt = self._current_receipt(request)
        else:
            state = self._checkout_state(request)
            answers = state.get("answers") or []
            cf = proofs.cached_file(state.get("cf"))
            receipt = {"name": cf.filename} if cf else None
        return get_template("pretix_transferproof/checkout_confirm.html").render({
            "event": self.event,
            "details": self._bank_details(),
            "answers": answers,
            "receipt": receipt,
        }, request=request)

    # ------------------------------------------------------------------ retry / change payment method
    def payment_prepare(self, request, payment):
        form = self.payment_form(request, payment.order)
        if self._file_not_sent(request):
            messages.error(request, _("Tu navegador no envió la imagen. Recarga la página e inténtalo de nuevo."))
            return False
        if not form.is_valid():
            return False
        key = payment_state_key(payment)
        old = request.session.get(key) or {}
        state = {"answers": extra_fields.answers_from(self.fields, form.cleaned_data)}
        new_file = form.cleaned_data.get("receipt")
        if new_file:
            proofs.discard_upload(old.get("cf"))
            state["cf"] = proofs.store_upload(request, new_file)
        elif proofs.cached_file(old.get("cf")):
            state["cf"] = old["cf"]  # uploaded in an earlier attempt that was not confirmed yet
        else:
            # Keep the receipt the buyer already sent for this order, unless they upload a new one.
            existing = proofs.proof_of(payment) or proofs.latest_proof_of_order(payment.order)
            if existing:
                state["copy_from"] = existing.pk
            elif self.receipt_required:
                form.add_error("receipt", _("Sube el comprobante para continuar."))
                messages.error(request, _("Sube el comprobante para continuar."))
                return False
        request.session[key] = state
        return True

    def execute_payment(self, request, payment):
        from .models import TransferProof

        key = payment_state_key(payment)
        state = request.session.get(key) if request is not None else None
        if state is not None:
            copy_from = TransferProof.objects.filter(
                pk=state.get("copy_from"), payment__order=payment.order,
            ).first() if state.get("copy_from") else None
            proofs.attach(payment, answers=state.get("answers") or [],
                          cf=proofs.cached_file(state.get("cf")), copy_from=copy_from)
            request.session.pop(key, None)
        elif proofs.pending_from_meta(payment.order):
            proofs.attach_from_order_meta(payment.order)  # safety net if the order_placed hook failed
        if self.receipt_required and not proofs.proof_of(payment):
            raise PaymentException(_("Falta el comprobante de transferencia. Súbelo para completar el pago."))
        return None

    # ------------------------------------------------------------------ after the order exists
    def proof_url(self, payment):
        order = payment.order
        return eventreverse(self.event, "plugins:pretix_transferproof:order.download", kwargs={
            "order": order.code, "secret": order.secret, "payment": payment.pk,
        })

    def payment_pending_render(self, request, payment) -> str:
        proof = proofs.proof_of(payment)
        return get_template("pretix_transferproof/pending.html").render({
            "event": self.event,
            "order": payment.order,
            "amount": payment.amount,
            "details": self._bank_details(),
            "proof": proof,
            "proof_url": self.proof_url(payment) if proof else None,
            "answers": proofs.answers_of(payment),
        }, request=request)

    def order_pending_mail_render(self, order, payment) -> str:
        nl = "  \n"
        lines = [
            gettext("Transfiere el valor total a esta cuenta:"),
            "",
            nl.join(line.strip() for line in self._bank_details().splitlines() if line.strip()),
            "",
            nl.join([
                "**%s:** %s" % (gettext("Monto"), money_filter(payment.amount, self.event.currency)),
                "**%s:** %s" % (gettext("Referencia"), order.code),
            ]),
            "",
        ]
        if proofs.proof_of(payment):
            lines.append(gettext("Recibimos tu comprobante. Confirmaremos el pago cuando lo revisemos."))
        else:
            lines.append(gettext("Cuando transfieras, sube el comprobante desde el enlace de tu pedido."))
        return "\n".join(lines)

    def payment_control_render(self, request, payment) -> str:
        from django.urls import reverse

        proof = proofs.proof_of(payment)
        url = reverse("plugins:pretix_transferproof:download", kwargs={
            "organizer": self.event.organizer.slug, "event": self.event.slug,
            "code": payment.order.code, "payment": payment.pk,
        }) if proof else None
        return get_template("pretix_transferproof/control.html").render({
            "proof": proof, "url": url, "answers": proofs.answers_of(payment),
        }, request=request)

    def payment_control_render_short(self, payment) -> str:
        return gettext("Comprobante adjunto") if proofs.proof_of(payment) else gettext("Sin comprobante")

    def api_payment_details(self, payment):
        proof = proofs.proof_of(payment)
        return {
            "receipt": bool(proof),
            "receipt_uploaded": proof.created.isoformat() if proof else None,
            "answers": proofs.answers_of(payment),
        }

    def shred_payment_info(self, obj):
        if isinstance(obj, OrderPayment):
            proof = proofs.proof_of(obj)
            if proof:
                proof.delete()  # the image file is removed by the post_delete handler
        super().shred_payment_info(obj)
