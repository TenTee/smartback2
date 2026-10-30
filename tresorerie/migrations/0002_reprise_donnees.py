"""Comptes et catégories par défaut, puis reprise de l'historique dans le journal de trésorerie :
paiements de scolarité, anciennes recettes et anciennes dépenses (dont les salaires payés)."""
from django.db import migrations
from django.utils import timezone

CATEGORIES = [
    ("SCO-INS", "Frais d'inscription", "recette", "7061", True),
    ("SCO-FOR", "Frais de formation (scolarité)", "recette", "7062", True),
    ("REC-EXA", "Frais d'examen et de dossier", "recette", "7063", False),
    ("REC-SUB", "Subventions et dons", "recette", "71", False),
    ("REC-LOC", "Locations d'infrastructures", "recette", "7083", False),
    ("REC-VEN", "Ventes de produits et services", "recette", "701", False),
    ("REC-AUT", "Autres produits", "recette", "758", True),
    ("SAL", "Salaires et rémunérations", "depense", "661", True),
    ("CHS", "Charges sociales (CNPS…)", "depense", "664", False),
    ("VAC", "Vacations des formateurs", "depense", "6324", False),
    ("LOY", "Loyers et charges locatives", "depense", "622", False),
    ("EAU", "Eau, électricité, énergie", "depense", "605", False),
    ("FOU", "Fournitures de bureau et consommables", "depense", "604", False),
    ("PED", "Matériel et supports pédagogiques", "depense", "6047", False),
    ("ENT", "Entretien, réparations et nettoyage", "depense", "624", False),
    ("TEL", "Téléphone, internet, logiciels", "depense", "628", False),
    ("TRA", "Transports et déplacements", "depense", "618", False),
    ("COM", "Communication et publicité", "depense", "627", False),
    ("HON", "Honoraires et prestations", "depense", "632", False),
    ("ACT", "Activités extrascolaires et événements", "depense", "638", False),
    ("BAN", "Frais bancaires et mobile money", "depense", "631", False),
    ("IMP", "Impôts et taxes", "depense", "64", False),
    ("INV", "Investissements (équipements, mobilier)", "depense", "24", False),
    ("DEP-AUT", "Autres charges", "depense", "658", True),
]
MODES = {"cash": "especes", "mobile_money": "mobile_money", "orange_money": "mobile_money", "virement": "virement", "cheque": "cheque"}
ANC_DEP = {"Materiel": "PED", "Entretien": "ENT", "Logistique": "TRA", "Activites": "ACT", "Autres": "DEP-AUT"}
ANC_REC = {"Inscription": "SCO-INS", "Examen": "REC-EXA", "Subvention": "REC-SUB", "Activite": "REC-AUT",
           "Location": "REC-LOC", "Vente": "REC-VEN", "Autres": "REC-AUT"}


def reprise(apps, schema_editor):
    Categorie = apps.get_model("tresorerie", "CategorieFinance")
    Compte = apps.get_model("tresorerie", "CompteTresorerie")
    Operation = apps.get_model("tresorerie", "Operation")
    Paiement = apps.get_model("paiements", "Paiement")
    Depense = apps.get_model("depenses", "Depense")
    Revenu = apps.get_model("revenus", "Revenu")

    cats = {}
    for i, (code, libelle, sens, cpt, systeme) in enumerate(CATEGORIES):
        cats[code], _ = Categorie.objects.get_or_create(code=code, defaults={
            "libelle": libelle, "sens": sens, "compte_comptable": cpt, "systeme": systeme, "ordre": i})
    if not Compte.objects.exists():
        Compte.objects.create(nom="Caisse principale", type="caisse", ordre=0)
        Compte.objects.create(nom="Banque principale", type="banque", ordre=1)
        Compte.objects.create(nom="Mobile Money", type="mobile", ordre=2)
    caisse = Compte.objects.filter(type="caisse").first() or Compte.objects.first()
    par_type = {t: Compte.objects.filter(type=t).first() or caisse for t in ("caisse", "banque", "mobile")}

    compteurs = {}

    def numero(type_, date):
        prefixe = {"recette": "REC", "depense": "DEP"}[type_]
        cle = (prefixe, date.year)
        compteurs[cle] = compteurs.get(cle, 0) + 1
        return f"{prefixe}-{date.year}-{compteurs[cle]:06d}"

    lignes = []
    for p in Paiement.objects.all().order_by("date_paiement", "id"):
        mode = MODES.get(p.moyen_paiement or "cash", "especes")
        date = timezone.localtime(p.date_paiement).date() if p.date_paiement else timezone.localdate()
        compte = par_type["caisse" if mode == "especes" else ("mobile" if mode == "mobile_money" else "banque")]
        nom = ""
        if p.etudiant_id:
            nom = apps.get_model("etudiants", "Etudiant").objects.filter(pk=p.etudiant_id).values_list("nom", flat=True).first() or ""
        lignes.append(dict(type="recette", date=date, montant=p.montant_paye, compte=compte, mode=mode,
                           categorie=cats["SCO-INS" if p.paiement_type == "INSCRIPTION" else "SCO-FOR"],
                           libelle=(f"{'Inscription' if p.paiement_type == 'INSCRIPTION' else 'Scolarité'} — {nom}").strip(" —")[:255],
                           tiers=nom[:200], etudiant_id=p.etudiant_id, annee_academique_id=p.annee_academique_id,
                           statut="validee", source="scolarite", source_type="paiement", source_id=p.pk))
    for r in Revenu.objects.all().order_by("date_entree", "id"):
        st = (r.statut or "").lower()
        lignes.append(dict(type="recette", date=r.date_entree or timezone.localdate(), montant=r.montant, compte=caisse, mode="especes",
                           categorie=cats[ANC_REC.get(r.categorie, "REC-AUT")], libelle=str(r.libelle)[:255],
                           tiers=str(r.responsable or "")[:200], statut="validee" if st.startswith("valid") else ("rejetee" if st.startswith("rejet") else "en_attente"),
                           source="ancien", source_type="revenu", source_id=r.pk))
    for d in Depense.objects.all().order_by("date_depense", "id"):
        st = (d.statut or "").lower()
        statut = "validee" if st.startswith("valid") else ("rejetee" if st.startswith("rejet") else "en_attente")
        salaire = str(d.libelle or "").lower().startswith("salaire")
        lignes.append(dict(type="depense", date=d.date_depense or timezone.localdate(), montant=d.montant,
                           compte=caisse if statut == "validee" else None, mode="especes",
                           categorie=cats["SAL" if salaire else ANC_DEP.get(d.categorie, "DEP-AUT")], libelle=str(d.libelle)[:255],
                           statut=statut, source="paie" if salaire else "ancien", source_type="depense", source_id=d.pk))
    lignes.sort(key=lambda x: (x["date"], x["type"]))
    existants = set(Operation.objects.exclude(source_type="").values_list("source_type", "source_id"))
    a_creer = []
    for l in lignes:
        if (l["source_type"], l["source_id"]) in existants:
            continue
        a_creer.append(Operation(numero=numero(l["type"], l["date"]), valide_le=timezone.now() if l["statut"] == "validee" else None, **l))
    Operation.objects.bulk_create(a_creer, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("tresorerie", "0001_initial"),
        ("paiements", "0005_paiement_compte_tresorerie"),
        ("depenses", "0001_initial"),
        ("revenus", "0001_initial"),
        ("etudiants", "0005_inscription_statut"),
    ]

    operations = [migrations.RunPython(reprise, migrations.RunPython.noop)]
