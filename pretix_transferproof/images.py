"""
Receipt validation. Every upload is decoded and re-encoded, so what we store is always a clean
PNG/JPEG without metadata (EXIF can carry GPS data), correctly rotated and reasonably sized.
"""
import warnings
from io import BytesIO

from django import forms
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 2400  # long side of the stored image; plenty to read a receipt
MAX_PNG_PIXELS = 20_000_000  # PNGs are decoded in full: 20 MP covers very long phone screenshots
ACCEPTED_FORMATS = {"PNG", "JPEG", "MPO"}  # MPO = JPEG + extra frames, produced by some phone cameras


def max_upload_size():
    return getattr(settings, "FILE_UPLOAD_MAX_SIZE_OTHER", 10 * 1024 * 1024)


def validate_and_reencode(uploaded):
    if uploaded.size and uploaded.size > max_upload_size():
        raise forms.ValidationError(
            _("El archivo supera el tamaño máximo de %(mb)s MB.") % {"mb": max_upload_size() // (1024 * 1024)}
        )
    try:
        uploaded.seek(0)
    except (AttributeError, OSError):
        pass
    data = uploaded.read()

    with warnings.catch_warnings():
        # Pillow only *warns* between ~89 and ~179 megapixels; treat that as an error.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(BytesIO(data))
            fmt = image.format
            if fmt not in ACCEPTED_FORMATS:
                raise forms.ValidationError(_("Solo se aceptan imágenes PNG o JPG."))
            if fmt == "PNG" and image.width * image.height > MAX_PNG_PIXELS:
                raise forms.ValidationError(_("La imagen es demasiado grande."))
            if fmt in ("JPEG", "MPO"):
                # Decode big photos at reduced resolution: a 48 MP photo never needs 150 MB of RAM.
                image.draft("RGB", (MAX_SIDE, MAX_SIDE))
            image.load()
            image = ImageOps.exif_transpose(image)  # phone photos store "rotate me" in EXIF
        except forms.ValidationError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError(_("La imagen es demasiado grande.")) from None
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
            raise forms.ValidationError(_("El archivo no es una imagen PNG o JPG válida.")) from None

    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = BytesIO()
    if fmt == "PNG":
        if image.mode not in ("RGB", "RGBA", "L", "LA"):
            image = image.convert("RGBA")
        image.save(out, format="PNG", optimize=True)
        name = "comprobante.png"
    else:
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(out, format="JPEG", quality=85, optimize=True)
        name = "comprobante.jpg"
    return ContentFile(out.getvalue(), name=name)
