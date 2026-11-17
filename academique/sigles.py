"""Sigles courts des classes pour les tableaux : « Développement d'applications · Formations
Qualifiantes · 1 » → « DA-FQ1 ».

Le code saisi sur la filière / le cycle / le niveau est prioritaire ; sinon on prend les initiales.
Deux filières aux mêmes initiales (ex. « Développement d'applications » et « Data analyst ») sont
départagées automatiquement (« DEVA » / « DATA »).
"""
import re
import time
import unicodedata

MOTS_VIDES = {"de", "des", "du", "d", "la", "le", "les", "l", "aux", "au", "et", "en", "pour", "a", "à", "sur", "par"}
_cache = {"t": 0, "filieres": {}}


def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _mots(nom):
    return [m for m in re.split(r"[\s'’\-_/().,]+", _sans_accents(nom)) if m and m.lower() not in MOTS_VIDES]


def initiales(nom):
    mots = _mots(nom)
    if len(mots) == 1 and not mots[0].isdigit():
        return mots[0][:3].upper()  # un seul mot : « Cybersécurité » → « CYB »
    return "".join(m if m.isdigit() else m[0] for m in mots).upper()


def _sigle_long(nom):
    mots = _mots(nom)
    if not mots:
        return ""
    return (mots[0][:3] + "".join(m[0] for m in mots[1:])).upper()


def sigles_filieres():
    """{id filière: sigle} pour toutes les filières, collisions départagées (cache 60 s)."""
    if time.time() - _cache["t"] < 60 and _cache["filieres"]:
        return _cache["filieres"]
    from .models import Filiere
    filieres = list(Filiere.objects.values("id", "nom", "code"))
    base = {f["id"]: (f["code"] or "").strip().upper() or initiales(f["nom"]) for f in filieres}
    comptes = {}
    for s in base.values():
        comptes[s] = comptes.get(s, 0) + 1
    res = {}
    for f in filieres:
        s = base[f["id"]]
        if comptes[s] > 1 and not (f["code"] or "").strip():
            s = _sigle_long(f["nom"]) or s
        res[f["id"]] = s
    _cache.update(t=time.time(), filieres=res)
    return res


def sigle_niveau(niveau):
    if not niveau:
        return ""
    if (getattr(niveau, "code", "") or "").strip():
        return niveau.code.strip().upper()
    chiffres = re.findall(r"\d+", niveau.nom or "")
    return chiffres[0] if chiffres else initiales(niveau.nom)


def sigle_classe(classe):
    if not classe:
        return ""
    f = sigles_filieres().get(classe.filiere_id) or initiales(getattr(classe.filiere, "nom", ""))
    c = (getattr(classe.cycle, "code", "") or "").strip().upper() or initiales(getattr(classe.cycle, "nom", ""))
    n = sigle_niveau(classe.niveau)
    return "-".join(p for p in (f, f"{c}{n}") if p)
