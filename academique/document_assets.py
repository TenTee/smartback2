"""
Outils pour intégrer les images de l'établissement (logo, signature, cachet, photo)
directement dans les réponses JSON sous forme de data URL.

Cela permet au front de générer des PDF (jsPDF) sans dépendre des en-têtes CORS
du serveur de fichiers média.
"""
import base64
import mimetypes

MAX_EMBED_SIZE = 3 * 1024 * 1024  # au-delà, l'image est réduite avant d'être intégrée
MAX_DIMENSION = 1200  # px : largement suffisant pour un logo / cachet imprimé


def _normaliser(content):
    """Ré-encode l'image en PNG (format réel détecté, quelle que soit l'extension), réduite si besoin.
    Retourne (mime, octets) ou None si ce n'est pas une image lisible par Pillow (ex. SVG)."""
    try:
        from io import BytesIO

        from PIL import Image, ImageOps

        img = Image.open(BytesIO(content))
        img.load()
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
        out = BytesIO()
        img.save(out, format="PNG", optimize=True)
        return "image/png", out.getvalue()
    except Exception:
        return None


def file_to_data_url(field_file):
    """Convertit un FieldFile (ImageField/FileField) en data URL base64 (PNG normalisé), ou None."""
    if not field_file:
        return None
    try:
        field_file.open("rb")
        try:
            content = field_file.read()
        finally:
            field_file.close()
    except Exception:
        return None
    if not content:
        return None
    norm = _normaliser(content)
    if norm:
        mime, content = norm
    else:
        if len(content) > MAX_EMBED_SIZE:
            return None
        mime = mimetypes.guess_type(field_file.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def etablissement_images(config):
    """Images de l'établissement utiles aux documents officiels."""
    return {
        "logo": file_to_data_url(config.logo),
        "logo_entete": file_to_data_url(config.logo_entete),
        "signature_directeur": file_to_data_url(config.signature_directeur),
        "cachet": file_to_data_url(getattr(config, "cachet", None)),
    }


def wants_embedded_images(request):
    return str(request.query_params.get("embed_images", "")).lower() in ("1", "true", "yes", "oui")
