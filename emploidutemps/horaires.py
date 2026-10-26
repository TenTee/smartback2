"""Contrôle des horaires d'un créneau : pause de la classe et amplitude de la journée."""
import datetime


def _hm(t):
    return t.strftime("%H:%M")


def erreur_horaires(classe, heure_debut, heure_fin, verifier_journee=True):
    """Message d'erreur si le créneau tombe sur la pause de la classe ou hors de la journée, sinon None."""
    if classe is not None:
        h = classe.horaires()
    else:
        h = {"pause_debut": datetime.time(12, 0), "pause_fin": datetime.time(13, 0), "pause_source": "defaut",
             "debut_journee": None, "fin_journee": None}
    pd, pf = h["pause_debut"], h["pause_fin"]
    if pd and pf and heure_debut < pf and heure_fin > pd:
        origine = " de la classe" if h["pause_source"] == "classe" else ""
        return f"⏸️ Impossible de programmer une séance pendant la pause{origine} ({_hm(pd)}–{_hm(pf)})."
    if verifier_journee and h["debut_journee"] and h["fin_journee"]:
        if heure_debut < h["debut_journee"] or heure_fin > h["fin_journee"]:
            qui = "cette classe" if h.get("journee_source") == "classe" else "ce cycle"
            return f"🕒 Hors de la journée de {qui} ({_hm(h['debut_journee'])}–{_hm(h['fin_journee'])})."
    return None
