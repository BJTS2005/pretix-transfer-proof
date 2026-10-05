from django.urls import re_path

from . import views

urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/orders/(?P<code>[0-9A-Z]+)/transferproof/$",
        views.ControlProofDownload.as_view(),
        name="download",
    ),
]

event_patterns = [
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/transferproof/$",
        views.PresaleProofDownload.as_view(),
        name="order.download",
    ),
]
