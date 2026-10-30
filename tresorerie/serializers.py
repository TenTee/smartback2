from rest_framework import serializers

from .models import (
    Budget, CategorieFinance, ClotureCaisse, CompteTresorerie, Fournisseur, LigneBudget, Operation, Rapprochement,
)


def _nom(u):
    if not u:
        return ""
    return f"{u.prenoms or ''} {u.noms or ''}".strip() or u.username


class CompteSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    solde = serializers.SerializerMethodField()
    derniere_cloture = serializers.SerializerMethodField()

    class Meta:
        model = CompteTresorerie
        fields = ["id", "nom", "type", "type_libelle", "banque", "numero", "solde_initial", "date_solde_initial",
                  "actif", "ordre", "solde", "derniere_cloture"]

    def get_solde(self, obj):
        return float(obj.solde())

    def get_derniere_cloture(self, obj):
        c = obj.clotures.order_by("-date").first()
        return {"date": c.date, "ecart": float(c.ecart)} if c else None


class CategorieSerializer(serializers.ModelSerializer):
    sens_libelle = serializers.CharField(source="get_sens_display", read_only=True)

    class Meta:
        model = CategorieFinance
        fields = ["id", "code", "libelle", "sens", "sens_libelle", "compte_comptable", "actif", "systeme", "ordre"]
        read_only_fields = ["systeme"]


class FournisseurSerializer(serializers.ModelSerializer):
    total_paye = serializers.SerializerMethodField()
    nb_operations = serializers.SerializerMethodField()

    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "contact", "telephone", "email", "adresse", "niu", "rccm", "banque", "notes", "actif",
                  "total_paye", "nb_operations"]

    def get_total_paye(self, obj):
        from django.db.models import Sum
        return float(obj.operations.filter(statut=Operation.VALIDEE).aggregate(t=Sum("montant"))["t"] or 0)

    def get_nb_operations(self, obj):
        return obj.operations.exclude(statut=Operation.ANNULEE).count()


class OperationSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    mode_libelle = serializers.CharField(source="get_mode_display", read_only=True)
    source_libelle = serializers.CharField(source="get_source_display", read_only=True)
    compte_nom = serializers.CharField(source="compte.nom", read_only=True)
    compte_destination_nom = serializers.CharField(source="compte_destination.nom", read_only=True)
    categorie_libelle = serializers.CharField(source="categorie.libelle", read_only=True)
    categorie_code = serializers.CharField(source="categorie.code", read_only=True)
    fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    cree_par_nom = serializers.SerializerMethodField()
    approuve_par_nom = serializers.SerializerMethodField()
    valide_par_nom = serializers.SerializerMethodField()
    rapproche = serializers.SerializerMethodField()
    modifiable = serializers.SerializerMethodField()

    class Meta:
        model = Operation
        fields = [
            "id", "numero", "type", "type_libelle", "date", "montant", "compte", "compte_nom", "compte_destination",
            "compte_destination_nom", "categorie", "categorie_libelle", "categorie_code", "libelle", "tiers",
            "fournisseur", "fournisseur_nom", "etudiant", "etudiant_nom", "etudiant_matricule", "mode", "mode_libelle",
            "reference", "piece_jointe", "statut", "statut_libelle", "source", "source_libelle", "annee_academique",
            "date_echeance", "notes", "motif_rejet", "rapproche", "cree_par_nom", "cree_le", "approuve_par_nom",
            "approuve_le", "valide_par_nom", "valide_le", "modifiable",
        ]
        read_only_fields = ["numero", "statut", "source", "motif_rejet", "cree_le", "approuve_le", "valide_le"]

    def get_cree_par_nom(self, o):
        return _nom(o.cree_par)

    def get_approuve_par_nom(self, o):
        return _nom(o.approuve_par)

    def get_valide_par_nom(self, o):
        return _nom(o.valide_par)

    def get_rapproche(self, o):
        return bool(o.rapprochement_id)

    def get_modifiable(self, o):
        return o.source == "manuel" and o.statut not in (Operation.ANNULEE,) and not o.rapprochement_id

    def validate(self, data):
        inst = self.instance
        get = lambda k: data[k] if k in data else (getattr(inst, k) if inst else None)  # noqa: E731
        type_ = get("type")
        montant = get("montant")
        if montant is None or montant <= 0:
            raise serializers.ValidationError({"montant": ["Le montant doit être supérieur à 0."]})
        if type_ == Operation.VIREMENT:
            if not get("compte") or not get("compte_destination"):
                raise serializers.ValidationError({"compte_destination": ["Choisissez le compte de départ et le compte d'arrivée."]})
            if get("compte") == get("compte_destination"):
                raise serializers.ValidationError({"compte_destination": ["Les deux comptes doivent être différents."]})
        else:
            cat = get("categorie")
            if not cat:
                raise serializers.ValidationError({"categorie": ["Choisissez une catégorie."]})
            if cat.sens != type_:
                raise serializers.ValidationError({"categorie": [f"Cette catégorie est une catégorie de {cat.get_sens_display().lower()}."]})
            if type_ == Operation.RECETTE and not get("compte"):
                raise serializers.ValidationError({"compte": ["Choisissez la caisse ou le compte qui reçoit l'argent."]})
        return data


class ClotureSerializer(serializers.ModelSerializer):
    compte_nom = serializers.CharField(source="compte.nom", read_only=True)
    cree_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = ClotureCaisse
        fields = ["id", "compte", "compte_nom", "date", "solde_theorique", "solde_reel", "ecart", "billetage",
                  "commentaire", "cree_par_nom", "cree_le"]
        read_only_fields = ["solde_theorique", "ecart"]

    def get_cree_par_nom(self, o):
        return _nom(o.cree_par)


class RapprochementSerializer(serializers.ModelSerializer):
    compte_nom = serializers.CharField(source="compte.nom", read_only=True)
    nb_operations = serializers.SerializerMethodField()
    cree_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = Rapprochement
        fields = ["id", "compte", "compte_nom", "date_releve", "solde_releve", "solde_pointe", "ecart", "commentaire",
                  "nb_operations", "cree_par_nom", "cree_le"]
        read_only_fields = ["solde_pointe", "ecart"]

    def get_nb_operations(self, o):
        return o.operations.count()

    def get_cree_par_nom(self, o):
        return _nom(o.cree_par)


class LigneBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneBudget
        fields = ["id", "categorie", "montant_prevu", "notes"]


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ["id", "annee_academique", "commentaire"]
