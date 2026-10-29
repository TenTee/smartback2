"""Notes partielles : plusieurs évaluations sur 20 → note de CC ou de SN (moyenne pondérée par les coefficients)."""
from decimal import ROUND_HALF_UP, Decimal

from .models import EvaluationPartielle, Note, NotePartielle


def composantes_calculees(classe_id, module_id):
    """{"cc": bool, "sn": bool} : composante calculée à partir d'évaluations partielles."""
    presentes = set(EvaluationPartielle.objects.filter(classe_id=classe_id, module_id=module_id).values_list("composante", flat=True))
    return {"cc": "cc" in presentes, "sn": "sn" in presentes}


def moyenne(valeurs_coefs):
    vals = [(Decimal(v), Decimal(c)) for v, c in valeurs_coefs if v is not None]
    if not vals:
        return None
    total = sum(c for _, c in vals)
    if not total:
        return None
    return (sum(v * c for v, c in vals) / total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def note_principale(etudiant_id, classe, module):
    """Note « directe » (sans évaluation académique) de l'étudiant pour le module dans la classe."""
    session = module.semestre or "Semestre 1"
    note = Note.objects.filter(etudiant_id=etudiant_id, module=module, classe=classe, evaluation__isnull=True).order_by("id").first()
    if note is None:
        note = Note(etudiant_id=etudiant_id, module=module, classe=classe, session=session,
                    annee_academique=classe.annee_academique.libelle, annee_academique_ref=classe.annee_academique)
    return note


def recalculer(classe, module, etudiant_ids=None):
    """Met à jour note_cc / note_sn des étudiants à partir des évaluations partielles (la note finale suit)."""
    evals = list(EvaluationPartielle.objects.filter(classe=classe, module=module))
    par_comp = {"cc": [e for e in evals if e.composante == "cc"], "sn": [e for e in evals if e.composante == "sn"]}
    if not evals:
        return 0
    notes = {}
    for np in NotePartielle.objects.filter(evaluation__in=evals).select_related("evaluation"):
        notes.setdefault(np.etudiant_id, {})[np.evaluation_id] = np.valeur
    if etudiant_ids is None:
        from etudiants.models import Inscription
        etudiant_ids = set(Inscription.objects.filter(classe=classe).values_list("etudiant_id", flat=True)) | set(notes)
    maj = 0
    for etu_id in etudiant_ids:
        note = note_principale(etu_id, classe, module)
        avant = (note.note_cc, note.note_sn)
        valeurs = notes.get(etu_id, {})
        for comp, champ in (("cc", "note_cc"), ("sn", "note_sn")):
            if par_comp[comp]:
                setattr(note, champ, moyenne([(valeurs.get(e.id), e.coefficient) for e in par_comp[comp]]))
        if note.pk is None and note.note_cc is None and note.note_sn is None:
            continue  # rien à enregistrer pour cet étudiant
        if note.pk is None or (note.note_cc, note.note_sn) != avant:
            note.save()
            maj += 1
    return maj


def details_pour_etudiant(etudiant, notes):
    """Détail des évaluations partielles pour les notes d'un étudiant : {note_id: {"cc": [...], "sn": [...]}}."""
    cles = {(n.classe_id, n.module_id): n.id for n in notes if n.classe_id}
    if not cles:
        return {}
    evals = EvaluationPartielle.objects.filter(classe_id__in={c for c, _ in cles}, module_id__in={m for _, m in cles})
    valeurs = dict(NotePartielle.objects.filter(evaluation__in=evals, etudiant=etudiant).values_list("evaluation_id", "valeur"))
    res = {}
    for e in evals:
        nid = cles.get((e.classe_id, e.module_id))
        if nid is None:
            continue
        v = valeurs.get(e.id)
        res.setdefault(nid, {"cc": [], "sn": []})[e.composante].append({
            "libelle": e.libelle, "coefficient": float(e.coefficient), "date": e.date,
            "valeur": float(v) if v is not None else None,
        })
    return res
