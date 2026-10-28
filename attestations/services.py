"""Délivrance des certificats de scolarité et cartes d'étudiant (numérotation, registre, données imprimées)."""
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .models import DocumentDelivre


class DelivranceImpossible(Exception):
    pass


def annee_de_reference(annee_id=None):
    from academique.middleware import get_current_academic_year_id
    from academique.models import AnneeAcademique

    annee_id = annee_id or get_current_academic_year_id()
    annee = AnneeAcademique.objects.filter(pk=annee_id).first() if annee_id else None
    return annee or AnneeAcademique.objects.filter(est_active=True).first()


def inscription_de(etudiant, annee):
    qs = etudiant.inscriptions.select_related("classe__filiere", "classe__cycle", "classe__niveau", "niveau", "annee_academique_ref")
    if annee:
        ins = qs.filter(annee_academique_ref=annee).order_by("-id").first() or qs.filter(classe__annee_academique=annee).order_by("-id").first()
    else:
        ins = qs.order_by("-id").first()
    return ins


def verifier_eligibilite(etudiant, annee):
    """Le document n'est délivré qu'à un étudiant inscrit (statut « Inscrit ») pour l'année."""
    ins = inscription_de(etudiant, annee)
    libelle = annee.libelle if annee else "l'année en cours"
    if not ins:
        raise DelivranceImpossible(f"{etudiant.nom} n'est pas inscrit(e) pour {libelle}.")
    if ins.statut != "Inscrit":
        raise DelivranceImpossible(f"{etudiant.nom} est seulement pré-inscrit(e) pour {libelle} : l'inscription doit être validée par la scolarité.")
    return ins


def photo_de(etudiant):
    return etudiant.documents.filter(type_document__icontains="photo").order_by("-id").first()


def donnees_imprimees(etudiant, ins, annee):
    classe = ins.classe
    return {
        "nom": etudiant.nom,
        "matricule": etudiant.matricule,
        "date_naissance": etudiant.date_naissance.isoformat() if etudiant.date_naissance else None,
        "email": etudiant.email,
        "contact": etudiant.contact,
        "nom_parent": etudiant.nom_parent,
        "contact_parent": etudiant.whatsapp_parent,
        "filiere": getattr(classe.filiere, "nom", "") if classe else getattr(etudiant.filiere, "nom", ""),
        "cycle": getattr(classe.cycle, "nom", "") if classe and classe.cycle_id else "",
        "niveau": getattr(ins.niveau, "nom", "") or (getattr(classe.niveau, "nom", "") if classe else ""),
        "classe": classe.nom if classe else "",
        "annee_academique": annee.libelle if annee else ins.annee_academique,
        "annee_debut": annee.date_debut.isoformat() if annee and annee.date_debut else None,
        "annee_fin": annee.date_fin.isoformat() if annee and annee.date_fin else None,
    }


def _numero(type_, sequence, annee, etudiant):
    libelle = annee.libelle if annee else str(timezone.localdate().year)
    if type_ == DocumentDelivre.CERTIFICAT:
        return f"{sequence:04d}/CS/{libelle}"
    if type_ == DocumentDelivre.RELEVE:
        return f"{sequence:04d}/RN/{libelle}"
    return f"CE-{libelle.split('-')[0]}-{sequence:05d}"


def emettre(type_, etudiant, user=None, canal="administration", nouveau=False, annee=None):
    """Retourne le document en cours de validité (réimpression) ou en crée un nouveau.

    nouveau=True : annule le document précédent de l'année (duplicata, informations corrigées…).
    """
    annee = annee or annee_de_reference()
    ins = verifier_eligibilite(etudiant, annee)
    existant = DocumentDelivre.objects.filter(type=type_, etudiant=etudiant, annee_academique=annee, annule=False).order_by("-id").first()
    if existant and not nouveau:
        existant.nb_impressions += 1
        existant.derniere_impression = timezone.now()
        existant.save(update_fields=["nb_impressions", "derniere_impression"])
        return existant, False

    for _ in range(5):
        try:
            with transaction.atomic():
                if existant:
                    DocumentDelivre.objects.filter(pk=existant.pk).update(
                        annule=True, annule_le=timezone.now(), annule_par=user if getattr(user, "is_authenticated", False) else None,
                        motif_annulation="Remplacé par un nouveau document",
                    )
                seq = (DocumentDelivre.objects.filter(type=type_, annee_academique=annee).aggregate(m=Max("sequence"))["m"] or 0) + 1
                doc = DocumentDelivre.objects.create(
                    type=type_, sequence=seq, numero=_numero(type_, seq, annee, etudiant), etudiant=etudiant, inscription=ins,
                    classe=ins.classe, annee_academique=annee, donnees=donnees_imprimees(etudiant, ins, annee),
                    delivre_par=user if getattr(user, "is_authenticated", False) else None, canal=canal,
                    valide_jusqu_au=annee.date_fin if annee else None, derniere_impression=timezone.now(),
                )
                return doc, True
        except IntegrityError:
            continue  # numéro pris en même temps par une autre délivrance : on réessaie
    raise DelivranceImpossible("Numérotation impossible, réessayez.")


def statut(doc):
    if doc.annule:
        return "annule"
    if doc.valide_jusqu_au and doc.valide_jusqu_au < timezone.localdate():
        return "expire"
    return "valide"


def document_json(doc, avec_photo=True):
    from academique.document_assets import file_to_data_url

    photo = None
    if avec_photo:
        p = photo_de(doc.etudiant)
        photo = file_to_data_url(p.fichier) if p else None
    return {
        "id": doc.id, "type": doc.type, "type_libelle": doc.get_type_display(), "numero": doc.numero, "code": doc.code,
        "etudiant_id": doc.etudiant_id, "classe_id": doc.classe_id, "donnees": doc.donnees,
        "delivre_le": doc.delivre_le, "valide_jusqu_au": doc.valide_jusqu_au, "canal": doc.canal,
        "delivre_par": (f"{doc.delivre_par.prenoms or ''} {doc.delivre_par.noms or ''}".strip() or doc.delivre_par.username) if doc.delivre_par_id else "",
        "nb_impressions": doc.nb_impressions, "statut": statut(doc), "motif_annulation": doc.motif_annulation,
        "annule_le": doc.annule_le, "photo": photo,
    }


def etablissement_json():
    from academique.document_assets import etablissement_images
    from academique.models import ConfigurationEtablissement

    c = ConfigurationEtablissement.get_config()
    return {
        "nom": c.nom, "adresse": c.adresse, "ville": c.ville, "telephone": c.telephone, "email": c.email,
        "site_web": c.site_web, "slogan": getattr(c, "slogan", ""), "nom_directeur": c.nom_directeur,
        "titre_directeur": c.titre_directeur, "couleur_primaire": c.couleur_primaire, "couleur_secondaire": c.couleur_secondaire,
        "releve_config": getattr(c, "releve_config", None) or {},
        "images": etablissement_images(c),
    }


# ---------------------------------------------------------------------------
# Relevés de notes
# ---------------------------------------------------------------------------
def _contenu_releve(releve):
    """Résultats figés dans le registre (affichés par la page de vérification)."""
    semestres = []
    for sem in releve.get("semestres") or []:
        semestres.append({
            "session": sem.get("session"),
            "moyenne": sem.get("moyenne"),
            "credits_obtenus": sem.get("credits_obtenus"),
            "total_credits": sem.get("total_credits"),
            "notes": [
                {"code": n.get("code_ue") or "", "module": n.get("module_nom"), "credits": n.get("credits"), "note": n.get("note_finale")}
                for n in sem.get("notes") or []
            ],
        })
    r = releve.get("resume") or {}
    return {
        "moyenne_annuelle": r.get("moyenne_annuelle"),
        "mention": r.get("mention"),
        "credits_obtenus": r.get("credits_obtenus"),
        "total_credits": r.get("total_credits"),
        "rang": r.get("rang"),
        "effectif": r.get("effectif"),
        "semestres": semestres,
    }


def enregistrer_releve(etudiant, inscription, releve, user=None):
    """Inscrit le relevé au registre et renvoie {numero, code, …}.

    Même contenu que le dernier relevé valable de l'année → même numéro (réimpression).
    Notes modifiées → nouveau numéro ; l'ancien relevé est annulé (« remplacé »), son QR code l'indique.
    """
    import hashlib
    import json

    annee = inscription.classe.annee_academique if inscription and inscription.classe_id else annee_de_reference()
    resultats = _contenu_releve(releve)
    empreinte = hashlib.sha256(json.dumps(resultats, sort_keys=True, default=str).encode()).hexdigest()[:24]
    canal = "portail" if getattr(user, "etudiant_profile", None) is not None and _est_etudiant(user) else "administration"

    existant = DocumentDelivre.objects.filter(
        type=DocumentDelivre.RELEVE, etudiant=etudiant, annee_academique=annee, annule=False,
    ).order_by("-id").first()
    if existant and (existant.donnees or {}).get("empreinte") == empreinte:
        existant.nb_impressions += 1
        existant.derniere_impression = timezone.now()
        existant.save(update_fields=["nb_impressions", "derniere_impression"])
        return releve_json(existant)

    e = releve.get("etudiant") or {}
    donnees = {
        "nom": etudiant.nom, "matricule": etudiant.matricule,
        "date_naissance": etudiant.date_naissance.isoformat() if etudiant.date_naissance else None,
        "filiere": e.get("filiere"), "cycle": e.get("cycle"), "niveau": e.get("niveau"), "classe": e.get("classe"),
        "annee_academique": annee.libelle if annee else (releve.get("parametres") or {}).get("annee_academique"),
        "resultats": resultats, "empreinte": empreinte,
    }
    for _ in range(5):
        try:
            with transaction.atomic():
                if existant:
                    DocumentDelivre.objects.filter(pk=existant.pk).update(
                        annule=True, annule_le=timezone.now(), motif_annulation="Remplacé : notes mises à jour",
                        annule_par=user if getattr(user, "is_authenticated", False) else None,
                    )
                seq = (DocumentDelivre.objects.filter(type=DocumentDelivre.RELEVE, annee_academique=annee).aggregate(m=Max("sequence"))["m"] or 0) + 1
                doc = DocumentDelivre.objects.create(
                    type=DocumentDelivre.RELEVE, sequence=seq, numero=_numero(DocumentDelivre.RELEVE, seq, annee, etudiant),
                    etudiant=etudiant, inscription=inscription, classe=inscription.classe if inscription else None,
                    annee_academique=annee, donnees=donnees, canal=canal,
                    delivre_par=user if getattr(user, "is_authenticated", False) else None,
                    valide_jusqu_au=None, derniere_impression=timezone.now(),
                )
                return releve_json(doc)
        except IntegrityError:
            continue
    raise DelivranceImpossible("Numérotation impossible, réessayez.")


def _est_etudiant(user):
    try:
        from notifications.services import profil
        return profil(user) == "etudiant"
    except Exception:  # noqa: BLE001
        return False


def releve_json(doc):
    return {"id": doc.id, "numero": doc.numero, "code": doc.code, "delivre_le": doc.delivre_le, "statut": statut(doc)}
