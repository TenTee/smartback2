from django.core.exceptions import ValidationError


def generate_classe_name(specialite, niveau, annee_academique):
    parts = [
        getattr(specialite, "nom", None),
        getattr(niveau, "nom", None),
        getattr(annee_academique, "libelle", None),
    ]
    return " - ".join(part for part in parts if part)


def validate_classe_hierarchy(classe):
    if classe.cycle_id and classe.niveau_id and classe.niveau.cycle_id and classe.niveau.cycle_id != classe.cycle_id:
        raise ValidationError({"niveau": "Le niveau sélectionné n'appartient pas au cycle fourni."})

    if classe.specialite_id and classe.cycle_id and classe.cycle.specialite_id != classe.specialite_id:
        raise ValidationError({"cycle": "Le cycle sélectionné n'appartient pas à la spécialité fournie."})


def sync_legacy_niveau_fields(niveau):
    if niveau.cycle_id and getattr(niveau.cycle, "specialite_id", None):
        filiere = niveau.cycle.specialite.filiere
        if filiere and filiere.formation_id and niveau.formation_id != filiere.formation_id:
            raise ValidationError({"formation": "Le niveau n'est pas cohérent avec la filière héritée de son cycle."})
