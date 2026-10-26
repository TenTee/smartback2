"""Notifications destinées aux étudiants (portail) et aux formateurs (espace formateur)."""
import datetime as dt

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .services import notifier_utilisateurs
from .signals import montant, sans_echec


def _h(t):
    return f"{t.hour}H{t.minute:02d}" if t.minute else f"{t.hour}H"


def _d(d):
    return d.strftime("%d/%m/%Y") if d else ""


def note20(v):
    try:
        return f"{float(v):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def compte_etudiant(etudiant):
    return getattr(etudiant, "user", None) if etudiant else None


def compte_formateur(formateur):
    return getattr(formateur, "user", None) if formateur else None


def comptes_etudiants_classe(classe_id):
    """Comptes des étudiants inscrits dans une classe."""
    if not classe_id:
        return []
    from users.models import CustomUser
    return list(CustomUser.objects.filter(
        is_active=True, etudiant_profile__inscriptions__classe_id=classe_id,
    ).distinct())


def classes_du_module(module_id, formateur_id=None):
    """Classes de l'année active où le module est enseigné (affectations + emplois du temps)."""
    from academique.models import Affectation, AnneeAcademique
    from emploidutemps.models import EmploiDuTemps

    annee = AnneeAcademique.objects.filter(est_active=True).first()
    aff = Affectation.objects.filter(module_id=module_id)
    edt = EmploiDuTemps.objects.filter(module_id=module_id, classe__isnull=False)
    if formateur_id:
        aff = aff.filter(enseignant_id=formateur_id)
        edt = edt.filter(formateur_id=formateur_id)
    if annee:
        aff = aff.filter(classe__annee_academique=annee)
        edt = edt.filter(classe__annee_academique=annee)
    return set(aff.values_list("classe_id", flat=True)) | set(edt.values_list("classe_id", flat=True))


# ------------------------------------------------------------------ Notes
@receiver(pre_save, sender="notes.Note")
def _note_avant(sender, instance, **kwargs):
    ancienne = None
    if instance.pk:
        ancienne = sender.objects.filter(pk=instance.pk).values_list("note_finale", flat=True).first()
    instance._note_finale_avant = ancienne


@receiver(post_save, sender="notes.Note")
@sans_echec
def note_publiee(sender, instance, created, **kwargs):
    nf = instance.note_finale
    if nf is None:
        return
    avant = getattr(instance, "_note_finale_avant", None)
    if avant is not None and float(avant) == float(nf):
        return
    user = compte_etudiant(instance.etudiant)
    if not user:
        return
    module = getattr(instance.module, "nom", "")
    titre = f"{'Note mise à jour' if avant is not None else 'Nouvelle note'} : {module}"
    msg = f"Note finale : {note20(nf)}/20"
    if avant is not None:
        msg += f" (auparavant {note20(avant)}/20)"
    notifier_utilisateurs(
        [user], "etudiant", "note", titre, msg, lien="/portal/grades",
        niveau="succes" if float(nf) >= 10 else "info", cle=f"note-{instance.pk}-{note20(nf)}",
    )


# ------------------------------------------------------------------ Paiements
@receiver(post_save, sender="paiements.Paiement")
@sans_echec
def paiement_etudiant(sender, instance, created, **kwargs):
    if not created or not instance.etudiant_id:
        return
    user = compte_etudiant(instance.etudiant)
    if not user:
        return
    type_ = "d'inscription" if instance.paiement_type == "INSCRIPTION" else "de formation"
    reste = ""
    if instance.solde_restant is not None:
        reste = " · solde réglé" if float(instance.solde_restant) <= 0 else f" · reste à payer {montant(instance.solde_restant)}"
    notifier_utilisateurs(
        [user], "etudiant", "paiement", f"Paiement enregistré : {montant(instance.montant_paye)}",
        f"Frais {type_}{reste}", lien="/portal/finance", niveau="succes",
    )


# ------------------------------------------------------------------ Assiduité
@receiver(post_save, sender="assiduite.AssiduiteRecord")
@sans_echec
def assiduite_etudiant(sender, instance, created, **kwargs):
    if not created:
        return
    user = compte_etudiant(instance.etudiant)
    if not user:
        return
    horaire = f" ({_h(instance.heure_debut)} - {_h(instance.heure_fin)})" if instance.heure_debut and instance.heure_fin else ""
    quoi = "Absence enregistrée" if instance.type == "ABSENCE" else f"Retard de {instance.minutes_retard or '?'} min enregistré"
    notifier_utilisateurs(
        [user], "etudiant", f"assiduite_{instance.type.lower()}", quoi,
        f"{instance.module.nom}{horaire} le {_d(instance.date)}", lien="/portal/attendance", niveau="alerte",
    )


# ------------------------------------------------------------------ Inscription
@receiver(pre_save, sender="etudiants.Inscription")
def _inscription_avant(sender, instance, **kwargs):
    instance._statut_avant = sender.objects.filter(pk=instance.pk).values_list("statut", flat=True).first() if instance.pk else None


@receiver(post_save, sender="etudiants.Inscription")
@sans_echec
def inscription_validee(sender, instance, created, **kwargs):
    if instance.statut != "Inscrit" or getattr(instance, "_statut_avant", None) == "Inscrit":
        return
    user = compte_etudiant(instance.etudiant)
    if not user:
        return
    classe = getattr(instance.classe, "nom", "") if instance.classe_id else ""
    notifier_utilisateurs(
        [user], "etudiant", "inscription", "Inscription validée",
        f"Vous êtes inscrit(e) pour {instance.annee_academique}" + (f" en {classe}" if classe else ""),
        lien="/portal", niveau="succes", cle=f"inscription-{instance.pk}",
    )


# ------------------------------------------------------------------ Supports de cours
@receiver(pre_save, sender="formateurs.CoursDocument")
def _document_avant(sender, instance, **kwargs):
    instance._visible_avant = bool(
        sender.objects.filter(pk=instance.pk).values_list("est_visible_etudiants", flat=True).first()
    ) if instance.pk else False


@receiver(post_save, sender="formateurs.CoursDocument")
@sans_echec
def support_publie(sender, instance, created, **kwargs):
    if not instance.est_visible_etudiants or getattr(instance, "_visible_avant", False):
        return
    users = []
    for classe_id in classes_du_module(instance.module_id, instance.formateur_id):
        users += comptes_etudiants_classe(classe_id)
    formateur = f"{instance.formateur.nom} {getattr(instance.formateur, 'prenom', '') or ''}".strip()
    notifier_utilisateurs(
        users, "etudiant", "support_cours", f"Nouveau support de cours : {instance.module.nom}",
        f"{instance.titre} — partagé par {formateur}", lien="/portal/courses", cle=f"support-{instance.pk}",
    )


@receiver(post_save, sender="academique.Epreuve")
@sans_echec
def epreuve_partagee(sender, instance, created, **kwargs):
    if not created or not instance.est_partage:
        return
    from users.models import CustomUser
    users = CustomUser.objects.filter(
        is_active=True,
        etudiant_profile__inscriptions__classe__filiere_id=instance.filiere_id,
        etudiant_profile__inscriptions__classe__niveau_id=instance.niveau_id,
        etudiant_profile__inscriptions__classe__annee_academique_id=instance.annee_academique_id,
    ).distinct()
    notifier_utilisateurs(
        list(users), "etudiant", "epreuve", f"Nouvelle épreuve disponible : {instance.module.nom}",
        instance.nom, lien="/portal/exams-bank", cle=f"epreuve-{instance.pk}",
    )


# ------------------------------------------------------------------ Emploi du temps
def _edt_modifie(instance, supprime=False):
    """Une notification par jour et par classe (ou formateur) pour éviter le bruit lors de la saisie."""
    from django.utils import timezone
    jour = timezone.localdate().isoformat()
    module = getattr(instance.module, "nom", "")
    horaire = f"{instance.jour} {_h(instance.heure_debut)} - {_h(instance.heure_fin)}"
    detail = f"{'Cours retiré' if supprime else 'Dernière modification'} : {module}, {horaire}"
    if instance.date_debut:
        detail += f" (à partir du {_d(instance.date_debut)})"
    if instance.classe_id:
        notifier_utilisateurs(
            comptes_etudiants_classe(instance.classe_id), "etudiant", "edt",
            "Votre emploi du temps a été mis à jour", detail, lien="/portal/schedule",
            cle=f"edt-c{instance.classe_id}-{jour}",
        )
    user = compte_formateur(instance.formateur) if instance.formateur_id else None
    if user:
        classe = getattr(instance.classe, "nom", "") if instance.classe_id else ""
        notifier_utilisateurs(
            [user], "enseignement", "edt", "Votre emploi du temps a été mis à jour",
            detail + (f" — {classe}" if classe else ""), lien="/trainer/schedule",
            cle=f"edt-f{instance.formateur_id}-{jour}",
        )


@receiver(post_save, sender="emploidutemps.EmploiDuTemps")
@sans_echec
def edt_enregistre(sender, instance, **kwargs):
    _edt_modifie(instance)


@receiver(post_delete, sender="emploidutemps.EmploiDuTemps")
@sans_echec
def edt_supprime(sender, instance, **kwargs):
    _edt_modifie(instance, supprime=True)


# ------------------------------------------------------------------ Séances (formateur)
@receiver(pre_save, sender="emploidutemps.SeanceRealisee")
def _seance_avant(sender, instance, **kwargs):
    instance._statut_avant = sender.objects.filter(pk=instance.pk).values_list("statut", flat=True).first() if instance.pk else None


@receiver(post_save, sender="emploidutemps.SeanceRealisee")
@sans_echec
def seance_validee(sender, instance, created, **kwargs):
    if getattr(instance, "_statut_avant", None) == instance.statut:
        return
    user = compte_formateur(instance.formateur)
    if not user:
        return
    classe = getattr(instance.classe, "nom", "") if instance.classe_id else ""
    detail = f"{instance.module.nom}{' · ' + classe if classe else ''} — {_d(instance.date)} {_h(instance.heure_debut)}-{_h(instance.heure_fin)}"
    if instance.statut == sender.EFFECTUEE:
        heures = (instance.duree_minutes or 0) / 60
        notifier_utilisateurs(
            [user], "enseignement", "seance_validee", f"Séance validée ({heures:g} h comptabilisées)".replace(".", ","),
            detail, lien="/trainer/suivi", niveau="succes",
        )
    else:
        notifier_utilisateurs(
            [user], "enseignement", "seance_non_effectuee", "Séance marquée « non effectuée »",
            detail + (f" — {instance.commentaire}" if instance.commentaire else ""), lien="/trainer/suivi", niveau="alerte",
        )


# ------------------------------------------------------------------ Échéances (rappel quotidien)
def verifier_echeances_etudiants(jour=None, delai=3):
    """Prévient chaque étudiant d'une échéance proche (J-3) ou dépassée (une seule fois par tranche)."""
    from django.utils import timezone

    from academique.models import AnneeAcademique
    from etudiants.models import Inscription
    from paiements.schedule_resolver import compute_student_retard

    jour = jour or timezone.localdate()
    annee = AnneeAcademique.objects.filter(est_active=True).first()
    if not annee:
        return 0
    nb, vus = 0, set()
    qs = Inscription.objects.filter(classe__annee_academique=annee, etudiant__user__isnull=False).select_related("etudiant__user", "classe")
    for ins in qs:
        if ins.etudiant_id in vus:
            continue
        vus.add(ins.etudiant_id)
        user = ins.etudiant.user
        r = compute_student_retard(ins.etudiant, ins.classe, jour)
        for inst in r.get("installments") or []:
            if float(inst.get("balance_due") or 0) <= 0 or not inst.get("due_date"):
                continue
            due = inst["due_date"]
            if isinstance(due, str):
                due = dt.date.fromisoformat(due[:10])
            ecart = (due - jour).days
            label = inst.get("label") or f"Tranche {inst.get('order')}"
            if 0 <= ecart <= delai:
                quand = "aujourd'hui" if ecart == 0 else ("demain" if ecart == 1 else f"dans {ecart} jours")
                nb += len(notifier_utilisateurs(
                    [user], "etudiant", "echeance_proche", f"Échéance {quand} : {montant(inst['balance_due'])}",
                    f"{label} — à régler avant le {_d(due)}", lien="/portal/finance", niveau="alerte",
                    cle=f"ech-proche-{ins.etudiant_id}-{inst.get('order')}-{due.isoformat()}", inclure_auteur=True,
                ))
            elif ecart < 0:
                nb += len(notifier_utilisateurs(
                    [user], "etudiant", "echeance_retard", f"Échéance dépassée : {montant(inst['balance_due'])}",
                    f"{label} — échue le {_d(due)}. Merci de régulariser auprès du service financier.",
                    lien="/portal/finance", niveau="urgent",
                    cle=f"ech-retard-{ins.etudiant_id}-{inst.get('order')}-{due.isoformat()}", inclure_auteur=True,
                ))
    return nb


# ------------------------------------------------------------------ Annonces (formateurs)
@receiver(post_save, sender="communication.Communication")
@sans_echec
def annonce_publiee(sender, instance, created, **kwargs):
    if not created:
        return
    from users.models import CustomUser
    contenu = (instance.contenu or "").strip()
    notifier_utilisateurs(
        list(CustomUser.objects.filter(is_active=True, formateur_profile__isnull=False)), "enseignement", "annonce",
        f"Nouvelle annonce : {instance.titre}", contenu[:160] + ("…" if len(contenu) > 160 else ""),
        lien="/trainer/communication",
    )
