from django.db import migrations


def seed_academic_hierarchy(apps, schema_editor):
    Faculte = apps.get_model("academique", "Faculte")
    Domaine = apps.get_model("academique", "Domaine")
    Filiere = apps.get_model("academique", "Filiere")
    Specialite = apps.get_model("academique", "Specialite")
    Cycle = apps.get_model("academique", "Cycle")
    Classe = apps.get_model("academique", "Classe")
    AnneeAcademique = apps.get_model("academique", "AnneeAcademique")
    Formation = apps.get_model("formations", "Formation")
    Niveau = apps.get_model("formations", "Niveau")
    Inscription = apps.get_model("etudiants", "Inscription")
    Note = apps.get_model("notes", "Note")

    faculte, _ = Faculte.objects.get_or_create(
        nom="Faculte Generale",
        defaults={"code": "FG"},
    )
    domaine, _ = Domaine.objects.get_or_create(
        faculte=faculte,
        nom="Domaine General",
        defaults={"code": "DG"},
    )

    filieres_by_formation = {}
    for formation in Formation.objects.all():
        filiere, _ = Filiere.objects.get_or_create(
            formation=formation,
            defaults={
                "domaine": domaine,
                "nom": formation.intitule,
                "code": (formation.intitule or "")[:10].upper(),
            },
        )
        if filiere.domaine_id != domaine.id or not filiere.nom:
            filiere.domaine = domaine
            filiere.nom = filiere.nom or formation.intitule
            filiere.save(update_fields=["domaine", "nom"])
        specialite, _ = Specialite.objects.get_or_create(
            filiere=filiere,
            nom=formation.intitule,
            defaults={"code": (formation.intitule or "")[:10].upper()},
        )
        cycle, _ = Cycle.objects.get_or_create(
            specialite=specialite,
            nom="Cycle principal",
            defaults={"code": "CP", "ordre": 1},
        )
        filieres_by_formation[formation.id] = {
            "filiere": filiere,
            "specialite": specialite,
            "cycle": cycle,
        }

    for niveau in Niveau.objects.select_related("formation").all():
        hierarchy = filieres_by_formation.get(niveau.formation_id)
        if hierarchy and not niveau.cycle_id:
            niveau.cycle_id = hierarchy["cycle"].id
            niveau.save(update_fields=["cycle"])

    for inscription in Inscription.objects.select_related("niveau", "niveau__formation").all():
        if not inscription.annee_academique:
            continue

        annee, _ = AnneeAcademique.objects.get_or_create(libelle=inscription.annee_academique)
        hierarchy = filieres_by_formation.get(inscription.niveau.formation_id)
        if not hierarchy:
            continue

        classe, _ = Classe.objects.get_or_create(
            specialite=hierarchy["specialite"],
            cycle=hierarchy["cycle"],
            niveau=inscription.niveau,
            annee_academique=annee,
            defaults={"nom": f"{hierarchy['specialite'].nom} - {inscription.niveau.nom} - {annee.libelle}"},
        )

        if not classe.modules.exists():
            modules = list(inscription.niveau.modules.all())
            if not modules:
                modules = list(inscription.niveau.formation.modules.all())
            if modules:
                classe.modules.set(modules)

        update_fields = []
        if inscription.classe_id != classe.id:
            inscription.classe_id = classe.id
            update_fields.append("classe")
        if inscription.annee_academique_ref_id != annee.id:
            inscription.annee_academique_ref_id = annee.id
            update_fields.append("annee_academique_ref")
        if update_fields:
            inscription.save(update_fields=update_fields)

    for note in Note.objects.select_related("etudiant").all():
        inscription = (
            Inscription.objects.filter(
                etudiant_id=note.etudiant_id,
                annee_academique=note.annee_academique,
                classe__isnull=False,
            )
            .order_by("-date_inscription")
            .first()
        )
        if inscription and note.classe_id != inscription.classe_id:
            note.classe_id = inscription.classe_id
            note.save(update_fields=["classe"])


class Migration(migrations.Migration):

    dependencies = [
        ("academique", "0001_initial"),
        ("etudiants", "0009_inscription_annee_academique_ref_inscription_classe_and_more"),
        ("formations", "0005_niveau_cycle"),
        ("notes", "0004_note_classe_note_evaluation_alter_note_note_finale"),
    ]

    operations = [
        migrations.RunPython(seed_academic_hierarchy, migrations.RunPython.noop),
    ]
