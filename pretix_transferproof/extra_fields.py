"""Organizer-defined extra fields, stored as JSON in the provider settings."""
import json

from django import forms
from django.utils.translation import gettext_lazy as _

TYPES = ("text", "choice")
MAX_FIELDS = 20


def _normalize(entry):
    label = str(entry.get("label") or "").strip()
    ftype = entry.get("type") if entry.get("type") in TYPES else "text"
    options = []
    if ftype == "choice":
        seen = set()
        for o in entry.get("options") or []:
            o = str(o).strip()
            if o and o not in seen:
                seen.add(o)
                options.append(o)
    return {"label": label, "type": ftype, "required": bool(entry.get("required")), "options": options}


def parse(raw):
    """Tolerant reader used at checkout: skips anything malformed instead of failing."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    fields = []
    for entry in data[:MAX_FIELDS]:
        if not isinstance(entry, dict):
            continue
        f = _normalize(entry)
        if f["label"] and (f["type"] == "text" or f["options"]):
            fields.append(f)
    return fields


def clean(raw):
    """Strict validation for the settings page. Returns normalized JSON or raises ValidationError."""
    if not raw or not str(raw).strip():
        return "[]"
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise forms.ValidationError(_("JSON inválido: %(error)s") % {"error": e}) from None
    if not isinstance(data, list):
        raise forms.ValidationError(_("Debe ser una lista de campos: [ {...}, {...} ]."))
    if len(data) > MAX_FIELDS:
        raise forms.ValidationError(_("Máximo %(n)s campos.") % {"n": MAX_FIELDS})
    fields, labels = [], set()
    for i, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise forms.ValidationError(_("El campo %(n)s no es un objeto.") % {"n": i})
        if entry.get("type", "text") not in TYPES:
            raise forms.ValidationError(_("El campo %(n)s tiene un tipo desconocido (usa \"text\" o \"choice\").") % {"n": i})
        f = _normalize(entry)
        if not f["label"]:
            raise forms.ValidationError(_("El campo %(n)s no tiene etiqueta.") % {"n": i})
        if f["label"].casefold() in labels:
            raise forms.ValidationError(_("La etiqueta «%(label)s» está repetida.") % {"label": f["label"]})
        if f["type"] == "choice" and not f["options"]:
            raise forms.ValidationError(_("«%(label)s» es de opciones pero no tiene opciones.") % {"label": f["label"]})
        labels.add(f["label"].casefold())
        fields.append(f)
    return json.dumps(fields, ensure_ascii=False)


def form_fields(fields):
    out = {}
    for i, f in enumerate(fields):
        if f["type"] == "choice":
            out[f"extra_{i}"] = forms.ChoiceField(
                label=f["label"], required=f["required"],
                choices=[("", "---------")] + [(o, o) for o in f["options"]],
            )
        else:
            out[f"extra_{i}"] = forms.CharField(label=f["label"], required=f["required"], max_length=255)
    return out


def answers_from(fields, cleaned_data):
    answers = []
    for i, f in enumerate(fields):
        value = cleaned_data.get(f"extra_{i}")
        if value not in (None, ""):
            answers.append({"label": f["label"], "value": str(value).strip()})
    return answers


def initial_from(fields, answers):
    by_label = {a.get("label"): a.get("value") for a in answers or [] if isinstance(a, dict)}
    initial = {}
    for i, f in enumerate(fields):
        v = by_label.get(f["label"])
        if v is not None and (f["type"] == "text" or v in f["options"]):
            initial[f"extra_{i}"] = v
    return initial


def missing_required(fields, answers):
    given = {a.get("label") for a in answers or [] if a.get("value")}
    return [f["label"] for f in fields if f["required"] and f["label"] not in given]
