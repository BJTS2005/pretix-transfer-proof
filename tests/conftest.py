"""Fixture: an event with the transfer provider enabled and one ticket in the cart."""
import datetime
import json

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tp_helpers import BANK, EXTRA_FIELDS

from pretix.base.models import CartPosition, Event, Item, Organizer, Quota
from pretix.testutils.sessions import get_cart_session_key


class TP:
    pass


@pytest.fixture
def tp(db, client):
    e = TP()
    with scopes_disabled():
        e.orga = Organizer.objects.create(name="Org", slug="org")
        e.event = ev = Event.objects.create(
            organizer=e.orga, name="Festival", slug="fest", date_from=now() + datetime.timedelta(days=30),
            plugins="pretix_transferproof", live=True, currency="USD",
        )
        ev.settings.set("attendee_names_asked", False)
        ev.settings.set("timezone", "America/Guayaquil")
        ev.settings.set("payment_transferproof__enabled", True)
        ev.settings.set("payment_transferproof_bank_details", BANK)
        ev.settings.set("payment_transferproof_receipt_required", True)
        ev.settings.set("payment_transferproof_extra_fields", json.dumps(EXTRA_FIELDS))
        tax_rule = ev.tax_rules.create(rate=0, default=True)
        quota = Quota.objects.create(event=ev, name="Q", size=100)
        e.item = Item.objects.create(event=ev, name="Entrada", default_price=15, admission=True, tax_rule=tax_rule)
        quota.items.add(e.item)
    e.client = client
    client.get("/org/fest/")
    e.cart_id = get_cart_session_key(client, ev)
    with scopes_disabled():
        CartPosition.objects.create(event=ev, cart_id=e.cart_id, item=e.item, price=15,
                                    expires=now() + datetime.timedelta(minutes=30))
    session = client.session
    session["carts"][e.cart_id]["email"] = "comprador@example.com"
    session.save()
    return e
