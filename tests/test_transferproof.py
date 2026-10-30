"""End-to-end tests through pretix's real checkout, order and backend views."""
import io
import json
import re

import pytest
from bs4 import BeautifulSoup
from django import forms
from django.core import mail as djmail
from django_scopes import scopes_disabled
from PIL import Image
from tp_helpers import BANK, login_admin, pay_post, png_bytes, upload

from pretix.base.models import Order, OrderPayment

PAYMENT = "/org/fest/checkout/payment/"
CONFIRM = "/org/fest/checkout/confirm/"


def soup(r):
    return BeautifulSoup(r.content.decode(), "lxml")


def text(r):
    return soup(r).get_text(" ", strip=True)


def value(doc, name):
    el = doc.select_one(f'[name="{name}"]')
    if el is None:
        return None
    if el.name == "select":
        opt = el.select_one("option[selected]")
        return opt.get("value") if opt else None
    return el.get("value")


def place_order(tp, follow=True):
    r = tp.client.post(CONFIRM, follow=follow)
    with scopes_disabled():
        order = Order.objects.get(event=tp.event)
    return order, r


def payment_of(order):
    with scopes_disabled():
        return OrderPayment.objects.filter(order=order).order_by("-pk").first()


def proof_bytes(payment):
    with scopes_disabled():
        payment.refresh_from_db()
        f = payment.transferproof.file
        f.open("rb")
        try:
            return f.read()
        finally:
            f.close()


# ======================================================================= the user's list
def test_going_back_keeps_answers_and_receipt(tp):
    assert pay_post(tp.client).status_code == 302
    r = tp.client.get(PAYMENT)
    doc = soup(r)
    assert value(doc, "payment_transferproof-extra_0") == "Pichincha"
    assert value(doc, "payment_transferproof-extra_1") == "REF-123"
    assert "Ya subiste el comprobante" in text(r)
    # pressing "continue" again without picking the file again works, receipt still required
    r = pay_post(tp.client, receipt=False)
    assert r.status_code == 302 and "/checkout/confirm/" in r["Location"]


def test_confirm_page_shows_answers_and_receipt(tp):
    pay_post(tp.client)
    page = text(tp.client.get(CONFIRM))
    assert "Banco de origen Pichincha" in page and "REF-123" in page
    assert "Comprobante adjunto" in page


def test_answers_visible_to_buyer_and_organizer(tp, client):
    pay_post(tp.client)
    order, _ = place_order(tp)
    payment = payment_of(order)
    assert [a["value"] for a in payment.info_data["transferproof_answers"]] == ["Pichincha", "REF-123"]
    assert "REF-123" in text(tp.client.get(f"/org/fest/order/{order.code}/{order.secret}/"))
    login_admin(tp, client)
    assert "REF-123" in text(client.get(f"/control/event/org/fest/orders/{order.code}/"))


def test_change_method_page_is_prefilled_and_shows_receipt(tp):
    pay_post(tp.client)
    order, _ = place_order(tp)
    r = tp.client.get(f"/org/fest/order/{order.code}/{order.secret}/pay/change")
    doc = soup(r)
    assert value(doc, "payment_transferproof-extra_1") == "REF-123"
    assert "Ya subiste el comprobante" in text(r)


def test_retry_same_payment_replaces_receipt_and_answers(tp):
    pay_post(tp.client)
    order, _ = place_order(tp)
    payment = payment_of(order)
    before = proof_bytes(payment)
    base = f"/org/fest/order/{order.code}/{order.secret}/pay/{payment.pk}"
    r = tp.client.get(base + "/")
    assert value(soup(r), "payment_transferproof-extra_1") == "REF-123"
    r = pay_post(tp.client, url=base + "/", ref="REF-999", file=upload("nuevo.png", png_bytes(color=(0, 0, 255))))
    assert r.status_code == 302 and r["Location"].endswith("/confirm")
    assert "REF-999" in text(tp.client.get(base + "/confirm"))
    tp.client.post(base + "/confirm")
    payment.refresh_from_db()
    assert proof_bytes(payment) != before
    assert payment.info_data["transferproof_answers"][1]["value"] == "REF-999"


def test_change_method_without_new_file_keeps_previous_receipt(tp):
    pay_post(tp.client)
    order, _ = place_order(tp)
    old = payment_of(order)
    original = proof_bytes(old)
    base = f"/org/fest/order/{order.code}/{order.secret}/pay"
    r = pay_post(tp.client, url=base + "/change", receipt=False, ref="REF-777")
    assert r.status_code == 302 and "/confirm" in r["Location"]
    new = payment_of(order)
    assert new.pk != old.pk
    tp.client.post(f"{base}/{new.pk}/confirm")
    assert proof_bytes(new) == original
    new.refresh_from_db()
    assert new.info_data["transferproof_answers"][1]["value"] == "REF-777"


def test_optional_receipt_is_not_dropped_when_continuing_again(tp):
    tp.event.settings.set("payment_transferproof_receipt_required", False)
    pay_post(tp.client)
    pay_post(tp.client, receipt=False)
    order, _ = place_order(tp)
    assert proof_bytes(payment_of(order))


def test_optional_receipt_can_be_sent_later_from_the_order(tp):
    tp.event.settings.set("payment_transferproof_receipt_required", False)
    pay_post(tp.client, receipt=False)
    order, _ = place_order(tp)
    order_url = f"/org/fest/order/{order.code}/{order.secret}/"
    assert "Todavía no recibimos el comprobante" in text(tp.client.get(order_url))
    r = pay_post(tp.client, url=order_url + "pay/change")
    tp.client.post(r["Location"])
    assert "Recibimos tu comprobante" in text(tp.client.get(order_url))
    assert proof_bytes(payment_of(order))


def test_receipts_from_version_1_are_still_shown(tp, client):
    from pretix_transferproof.models import TransferProof
    pay_post(tp.client)
    order, _ = place_order(tp)
    p = payment_of(order)
    with scopes_disabled():
        p.info_data = {}
        p.save()
        TransferProof.objects.filter(payment=p).update(extra_answers={"Referencia": "V1-555"})
    login_admin(tp, client)
    assert "V1-555" in text(client.get(f"/control/event/org/fest/orders/{order.code}/"))


# ======================================================================= robustness
def test_receipt_attached_even_if_buyer_never_reaches_complete_page(tp):
    pay_post(tp.client)
    order, r = place_order(tp, follow=False)  # buyer closes the tab right after "Place order"
    assert "/complete" in r["Location"]
    payment = payment_of(order)
    assert proof_bytes(payment)
    assert payment.info_data["transferproof_answers"]
    with scopes_disabled():
        assert "transferproof" not in order.__class__.objects.get(pk=order.pk).meta_info_data


def test_complete_page_still_works_afterwards(tp):
    pay_post(tp.client)
    order, r = place_order(tp)
    assert "thanks" in r.redirect_chain[-1][0]
    assert "incomplete" not in text(r).lower()


def test_required_answer_missing_blocks_checkout(tp):
    r = pay_post(tp.client, ref="")
    assert r.status_code == 200
    assert "/checkout/confirm/" not in r.get("Location", "")


def test_form_sent_without_multipart_is_reported(tp):
    r = tp.client.post(PAYMENT, {
        "payment": "transferproof", "payment_transferproof-receipt": "comprobante.png",
        "payment_transferproof-extra_0": "Pichincha", "payment_transferproof-extra_1": "REF-1",
    })
    assert r.status_code == 200 and "no envió la imagen" in text(r)


def test_scripts_only_where_needed(tp):
    assert "pretix_transferproof/checkout.js" in tp.client.get(PAYMENT).content.decode()
    assert "pretix_transferproof/" not in tp.client.get("/org/fest/").content.decode()


# ======================================================================= security
def test_answers_are_escaped_in_backend(tp, client):
    pay_post(tp.client, ref='<img src=x id="pwned">')
    order, _ = place_order(tp)
    login_admin(tp, client)
    html = client.get(f"/control/event/org/fest/orders/{order.code}/").content.decode()
    assert '<img src=x id="pwned">' not in html
    assert "&lt;img src=x" in html


def test_backend_shows_each_payments_own_receipt(tp, client):
    pay_post(tp.client)
    order, _ = place_order(tp)
    first = payment_of(order)
    base = f"/org/fest/order/{order.code}/{order.secret}/pay"
    pay_post(tp.client, url=base + "/change", file=upload("otro.png", png_bytes(color=(0, 255, 0))))
    second = payment_of(order)
    tp.client.post(f"{base}/{second.pk}/confirm")
    login_admin(tp, client)
    html = client.get(f"/control/event/org/fest/orders/{order.code}/").content.decode()
    urls = sorted(set(re.findall(r'/orders/[A-Z0-9]+/transferproof/\d+/', html)))
    assert urls == sorted({f"/orders/{order.code}/transferproof/{first.pk}/",
                           f"/orders/{order.code}/transferproof/{second.pk}/"})
    for p in (first, second):
        r = client.get(f"/control/event/org/fest/orders/{order.code}/transferproof/{p.pk}/")
        assert b"".join(r.streaming_content) == proof_bytes(p)


def test_downloads_are_protected(tp, client):
    pay_post(tp.client)
    order, _ = place_order(tp)
    p = payment_of(order)
    assert tp.client.get(f"/org/fest/order/{order.code}/{order.secret}/transferproof/{p.pk}/").status_code == 200
    assert client.get(f"/org/fest/order/{order.code}/WRONGSECRET/transferproof/{p.pk}/").status_code == 404
    client.logout()
    r = client.get(f"/control/event/org/fest/orders/{order.code}/transferproof/{p.pk}/")
    assert r.status_code in (302, 403)


def test_shredding_removes_receipt(tp):
    pay_post(tp.client)
    order, _ = place_order(tp)
    p = payment_of(order)
    from pretix_transferproof.models import TransferProof
    with scopes_disabled():
        p.payment_provider.shred_payment_info(p)
        p.refresh_from_db()
        assert not TransferProof.objects.filter(payment=p).exists()
        assert "transferproof_answers" not in (p.info_data or {})


# ======================================================================= email / API / log
def test_order_email_contains_bank_details(tp):
    djmail.outbox = []
    pay_post(tp.client)
    order, _ = place_order(tp)
    body = "\n".join(m.body for m in djmail.outbox)
    assert "2200000000" in body and order.code in body and "Recibimos tu comprobante" in body


def test_api_details_and_order_log(tp):
    pay_post(tp.client)
    order, _ = place_order(tp)
    p = payment_of(order)
    details = p.payment_provider.api_payment_details(p)
    assert details["receipt"] is True and details["answers"][1]["value"] == "REF-123"
    with scopes_disabled():
        assert order.all_logentries().filter(action_type="pretix_transferproof.receipt.uploaded").exists()


# ======================================================================= settings page
def test_settings_keep_pretix_options_and_validate_json(tp, client):
    login_admin(tp, client)
    url = "/control/event/org/fest/settings/payment/transferproof"
    page = client.get(url).content.decode()
    for name in ("payment_transferproof__availability_date", "payment_transferproof__fee_abs",
                 "payment_transferproof__total_max"):
        assert f'name="{name}' in page, name
    assert "pretix_transferproof/extra_fields.js" in page
    data = {
        "payment_transferproof__enabled": "on",
        "payment_transferproof_bank_details": BANK,
        "payment_transferproof__restrict_to_sales_channels": "web",
        "payment_transferproof_extra_fields": '[{"label": "Banco", "type": "text",}]',
    }
    r = client.post(url, data)
    assert r.status_code == 200 and "JSON inválido" in text(r)
    data["payment_transferproof_extra_fields"] = json.dumps(
        [{"label": " Banco ", "type": "choice", "options": ["A", "A", " B "]}])
    r = client.post(url, data)
    assert r.status_code == 302
    tp.event.settings.flush()
    saved = json.loads(tp.event.settings.get("payment_transferproof_extra_fields"))
    assert saved == [{"label": "Banco", "type": "choice", "required": False, "options": ["A", "B"]}]


# ======================================================================= images
def _jpeg(size=(200, 100), orientation=None, fmt="JPEG"):
    img = Image.new("RGB", size, (255, 255, 255))
    buf = io.BytesIO()
    if fmt == "MPO":
        img.save(buf, "MPO", save_all=True, append_images=[Image.new("RGB", size, "blue")])
    elif orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def test_image_decoded_once_per_submit(tp, monkeypatch):
    import pretix_transferproof.payment as payment_module
    calls = []
    real = payment_module.validate_and_reencode
    monkeypatch.setattr(payment_module, "validate_and_reencode", lambda u: calls.append(1) or real(u))
    pay_post(tp.client)
    assert len(calls) == 1


def test_phone_photos_are_upright_and_mpo_accepted(db):
    from pretix_transferproof.images import validate_and_reencode
    out = Image.open(validate_and_reencode(upload("foto.jpg", _jpeg(orientation=6), "image/jpeg")))
    assert out.size == (100, 200)
    assert Image.open(validate_and_reencode(upload("foto.jpg", _jpeg(fmt="MPO"), "image/jpeg"))).format == "JPEG"
    assert validate_and_reencode(upload("comprobante.jfif", _jpeg(), "image/jpeg")).name == "comprobante.jpg"


def test_big_photos_are_downscaled(db):
    from pretix_transferproof.images import MAX_SIDE, validate_and_reencode
    out = Image.open(validate_and_reencode(upload("foto.jpg", _jpeg(size=(6000, 4000)), "image/jpeg")))
    assert max(out.size) == MAX_SIDE


def test_bombs_and_non_images_are_rejected(db):
    from pretix_transferproof.images import validate_and_reencode
    buf = io.BytesIO()
    Image.new("L", (10000, 9500), 255).save(buf, "PNG", optimize=True)
    with pytest.raises(forms.ValidationError):
        validate_and_reencode(upload("big.png", buf.getvalue()))
    with pytest.raises(forms.ValidationError):
        validate_and_reencode(upload("comprobante.png", b"%PDF-1.4 not an image"))
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(forms.ValidationError):
        validate_and_reencode(upload("comprobante.png", gif.getvalue()))
