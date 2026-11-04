"""Reprise de l'existant :
- un site « Campus principal » ;
- un emplacement par salle de l'emploi du temps ;
- les localisations saisies en texte libre deviennent des emplacements (rattachés à la salle de même nom s'il y en a une) ;
- un code QR pour chaque matériel ; les articles de papeterie / fournitures déjà suivis en quantité restent des équipements
  (à convertir à la main si besoin)."""
import secrets

from django.db import migrations


def reprendre(apps, schema_editor):
    Site = apps.get_model("inventaires", "Site")
    Emplacement = apps.get_model("inventaires", "Emplacement")
    Exemplaire = apps.get_model("inventaires", "Exemplaire")
    Salle = apps.get_model("emploidutemps", "Salle")

    salles = list(Salle.objects.all())
    textes = sorted({(e.localisation or "").strip() for e in Exemplaire.objects.exclude(localisation="")} - {""})
    if not salles and not textes and not Exemplaire.objects.exists():
        return
    site, _ = Site.objects.get_or_create(nom="Campus principal")
    par_nom = {}
    for s in salles:
        e, _ = Emplacement.objects.get_or_create(salle=s, defaults={"site": site, "nom": s.nom, "type": "salle", "code_qr": secrets.token_hex(6)})
        par_nom[s.nom.strip().lower()] = e
    for t in textes:
        if t.lower() not in par_nom:
            par_nom[t.lower()] = Emplacement.objects.create(site=site, nom=t[:150], type="autre", code_qr=secrets.token_hex(6))
    for ex in Exemplaire.objects.all().only("id", "localisation", "code_qr", "emplacement"):
        champs = {}
        if not ex.code_qr:
            champs["code_qr"] = secrets.token_hex(6)
        loc = (ex.localisation or "").strip().lower()
        if loc and loc in par_nom and not ex.emplacement_id:
            champs["emplacement"] = par_nom[loc]
        if champs:
            Exemplaire.objects.filter(pk=ex.pk).update(**champs)


class Migration(migrations.Migration):
    dependencies = [
        ("inventaires", "0002_localisation_maintenance_inventaire"),
    ]
    operations = [migrations.RunPython(reprendre, migrations.RunPython.noop)]
