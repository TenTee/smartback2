"""Optimisation des médias importés et service rapide des fichiers /media/.

1. Toute image envoyée sur la plateforme (photos, logos, scans de documents, photos de pannes…)
   est redimensionnée et recompressée à l'enregistrement, quel que soit le modèle :
   un signal pre_save générique traite chaque FileField / ImageField nouvellement rempli.
2. Les fichiers /media/ sont servis avec des en-têtes de cache : le navigateur ne les
   retélécharge plus à chaque affichage (réponse 304 si le fichier n'a pas changé).
"""
import io
import logging
import os

from django.core.files.base import ContentFile
from django.db.models import FileField
from django.utils.cache import patch_cache_control
from django.views.static import serve

logger = logging.getLogger(__name__)

EXTENSIONS_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
# Côté le plus long (px) selon l'usage ; au-delà l'image est réduite
TAILLE_MAX_DEFAUT = 2000          # scans de documents : lisibles à l'impression A4
TAILLE_MAX_PAR_DOSSIER = {
    "etablissement/": 1200,       # logos, cachet, signature
    "inventaire/": 1600,          # photos de matériel et de pannes
}
QUALITE_JPEG = 82
SEUIL_OCTETS = 150 * 1024         # en dessous, une image de taille raisonnable est laissée telle quelle


def _taille_max(chemin):
    for prefixe, taille in TAILLE_MAX_PAR_DOSSIER.items():
        if chemin.startswith(prefixe) or f"/{prefixe}" in chemin:
            return taille
    return TAILLE_MAX_DEFAUT


def optimiser_image(donnees, nom, taille_max=TAILLE_MAX_DEFAUT, conserver_format=False):
    """Renvoie (octets, nouveau_nom) d'une image optimisée, ou None si inutile / impossible.

    - corrige l'orientation EXIF (photos de téléphone) puis réduit au besoin ;
    - JPEG progressif qualité 82 pour les photos ;
    - PNG conservé (transparence des logos, cachets, signatures), optimisé et réduit ;
    - conserver_format : garde l'extension d'origine (réécriture sur place des fichiers existants).
    """
    from PIL import Image, ImageOps

    ext = os.path.splitext(nom)[1].lower()
    if ext not in EXTENSIONS_IMAGES:
        return None
    try:
        img = Image.open(io.BytesIO(donnees))
        img.load()
    except Exception:  # noqa: BLE001 — format non pris en charge : fichier laissé tel quel
        return None
    if getattr(img, "is_animated", False):
        return None

    trop_grande = max(img.size) > taille_max
    if len(donnees) < SEUIL_OCTETS and not trop_grande:
        return None

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001
        pass
    if trop_grande:
        img.thumbnail((taille_max, taille_max), Image.LANCZOS)

    transparente = img.mode in ("RGBA", "LA", "P") and (
        img.mode != "P" or "transparency" in img.info
    )
    sortie = io.BytesIO()
    base = os.path.splitext(nom)[0]
    if ext == ".png" or (transparente and not conserver_format):
        if conserver_format and ext != ".png":
            return None
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        img.save(sortie, format="PNG", optimize=True)
        nouveau_nom = f"{base}.png"
    else:
        if conserver_format and ext not in (".jpg", ".jpeg"):
            return None
        if img.mode != "RGB":
            fond = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode in ("RGBA", "LA"):
                fond.paste(img, mask=img.split()[-1])
            else:
                fond.paste(img.convert("RGB"))
            img = fond
        img.save(sortie, format="JPEG", quality=QUALITE_JPEG, optimize=True, progressive=True)
        nouveau_nom = nom if conserver_format else f"{base}.jpg"

    octets = sortie.getvalue()
    # Gain négligeable (< 5 %) : on garde l'original
    if len(octets) >= len(donnees) * 0.95 and not trop_grande:
        return None
    return octets, nouveau_nom


def optimiser_fichiers_avant_enregistrement(sender, instance, raw=False, **kwargs):
    """pre_save générique : optimise les images nouvellement importées dans tous les modèles."""
    if raw:
        return
    for champ in instance._meta.concrete_fields:
        if not isinstance(champ, FileField):
            continue
        fichier = getattr(instance, champ.attname)
        if not fichier or getattr(fichier, "_committed", True):
            continue  # pas de nouveau fichier sur ce champ
        try:
            nom = os.path.basename(fichier.name or "")
            fichier.seek(0)
            donnees = fichier.read()
            dossier = champ.upload_to if isinstance(champ.upload_to, str) else ""
            res = optimiser_image(donnees, nom, _taille_max(dossier))
            if res is None:
                fichier.seek(0)
                continue
            octets, nouveau_nom = res
            setattr(instance, champ.attname, ContentFile(octets, name=nouveau_nom))
            logger.info("Image optimisée %s : %d → %d Ko", nouveau_nom, len(donnees) // 1024, len(octets) // 1024)
        except Exception:  # noqa: BLE001 — l'optimisation ne doit jamais empêcher l'import
            logger.exception("Optimisation de l'image impossible")
            try:
                fichier.seek(0)
            except Exception:  # noqa: BLE001
                pass


def brancher():
    from django.db.models.signals import pre_save
    pre_save.connect(optimiser_fichiers_avant_enregistrement, dispatch_uid="smartcampus_optimisation_medias")


def servir_media(request, path, document_root=None):
    """Sert /media/ avec cache navigateur (7 jours) ; 304 si le fichier n'a pas changé."""
    reponse = serve(request, path, document_root=document_root)
    if reponse.status_code in (200, 304):
        patch_cache_control(reponse, public=True, max_age=7 * 24 * 3600)
    return reponse
