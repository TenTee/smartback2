"""
Outils pour intégrer les images de l'établissement (logo, signature, cachet, photo)
directement dans les réponses JSON sous forme de data URL.

Cela permet au front de générer des PDF (jsPDF) sans dépendre des en-têtes CORS
du serveur de fichiers média.
"""
import base64
import mimetypes

MAX_EMBED_SIZE = 3 * 1024 * 1024  # 3 Mo par image


def file_to_data_url(field_file):
    """Convertit un FieldFile (ImageField/FileField) en data URL base64, ou None."""
    if not field_file:
        return None
    try:
        if field_file.size and field_file.size > MAX_EMBED_SIZE:
            return None
        mime = mimetypes.guess_type(field_file.name)[0] or "image/png"
        field_file.open("rb")
        try:
            content = field_file.read()
        finally:
            field_file.close()
        return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
    except Exception:
        return None


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
