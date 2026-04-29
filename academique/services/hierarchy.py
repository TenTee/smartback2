from django.core.exceptions import ValidationError


def generate_classe_name(filiere, niveau, annee_academique):
    parts = [
        getattr(filiere, "nom", None),
        getattr(niveau, "nom", None),
        getattr(annee_academique, "libelle", None),
    ]
    return " - ".join(part for part in parts if part)


def validate_classe_hierarchy(classe):
    if classe.cycle_id and classe.niveau_id and classe.niveau.cycle_id and classe.niveau.cycle_id != classe.cycle_id:
        raise ValidationError({"niveau": "Le niveau sélectionné n'appartient pas au cycle fourni."})

    if classe.filiere_id and classe.cycle_id and classe.cycle.filiere_id != classe.filiere_id:
        raise ValidationError({"cycle": "Le cycle sélectionné n'appartient pas à la filière fournie."})
