import mimetypes
import os

from django.http import FileResponse, Http404
from django.views import View
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .models import TransferProof


class ControlProofDownload(EventPermissionRequiredMixin, View):
    permission = "can_view_orders"

    def get(self, request, *args, **kwargs):
        proof = TransferProof.objects.filter(
            payment__order__event=request.event,
            payment__order__code=kwargs["code"],
        ).first()
        if not proof or not proof.file:
            raise Http404()
        ftype = mimetypes.guess_type(proof.file.name)[0] or "application/octet-stream"
        response = FileResponse(proof.file, content_type=ftype)
        response["Content-Disposition"] = 'inline; filename="{}"'.format(
            os.path.basename(proof.file.name)
        )
        return response


class PresaleProofDownload(EventViewMixin, OrderDetailMixin, View):
    def get(self, request, *args, **kwargs):
        proof = TransferProof.objects.filter(payment__order=self.order).first()
        if not proof or not proof.file:
            raise Http404()
        ftype = mimetypes.guess_type(proof.file.name)[0] or "application/octet-stream"
        response = FileResponse(proof.file, content_type=ftype)
        response["Content-Disposition"] = 'inline; filename="{}"'.format(
            os.path.basename(proof.file.name)
        )
        return response
