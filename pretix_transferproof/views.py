import importlib.util
import mimetypes
import os

from django.http import FileResponse, Http404
from django.views import View

from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .models import TransferProof

# pretix >= 2026.3 has fine-grained permissions; older releases only know the legacy name
ORDERS_READ = (
    "event.orders:read" if importlib.util.find_spec("pretix.base.permissions") else "can_view_orders"
)


def serve(proof):
    if not proof or not proof.file:
        raise Http404()
    response = FileResponse(
        proof.file.open("rb"),
        content_type=mimetypes.guess_type(proof.file.name)[0] or "application/octet-stream",
    )
    response["Content-Disposition"] = 'inline; filename="{}"'.format(os.path.basename(proof.file.name))
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


class ControlProofDownload(EventPermissionRequiredMixin, View):
    permission = ORDERS_READ

    def get(self, request, *args, **kwargs):
        proofs = TransferProof.objects.filter(
            payment__order__event=request.event, payment__order__code=kwargs["code"],
        )
        if kwargs.get("payment"):
            proofs = proofs.filter(payment__pk=kwargs["payment"])
        return serve(proofs.order_by("-created").first())


class PresaleProofDownload(EventViewMixin, OrderDetailMixin, View):
    """Lets the buyer check the receipt they uploaded (order secret / customer login required)."""

    def get(self, request, *args, **kwargs):
        resp = self.verify_order_access() if hasattr(self, "verify_order_access") else None
        if resp:
            return resp
        if not self.order:
            raise Http404()
        return serve(TransferProof.objects.filter(payment__order=self.order, payment__pk=kwargs["payment"]).first())
