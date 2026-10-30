"""Helpers shared by the tests (kept out of conftest.py so they can be imported)."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled
from PIL import Image

from pretix.base.models import Team, User

BANK = "Banco Pichincha\nCuenta de ahorros 2200000000\nTitular: Festival S.A."
EXTRA_FIELDS = [
    {"label": "Banco de origen", "type": "choice", "required": True, "options": ["Pichincha", "Guayaquil"]},
    {"label": "Número de referencia", "type": "text", "required": True},
]


def png_bytes(w=60, h=40, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def upload(name="comprobante.png", data=None, ctype="image/png"):
    return SimpleUploadedFile(name, data if data is not None else png_bytes(), content_type=ctype)


def pay_post(client, receipt=True, bank="Pichincha", ref="REF-123", url="/org/fest/checkout/payment/", file=None):
    data = {"payment": "transferproof", "payment_transferproof-extra_0": bank, "payment_transferproof-extra_1": ref}
    if receipt:
        data["payment_transferproof-receipt"] = file or upload()
    return client.post(url, data)


def login_admin(e, client):
    with scopes_disabled():
        user = User.objects.create_user("admin@localhost", "admin")
        team = Team.objects.create(organizer=e.orga, all_events=True, all_event_permissions=True,
                                   all_organizer_permissions=True)
        team.members.add(user)
    client.force_login(user)
    return user
