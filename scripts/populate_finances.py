import random
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from academique.models import Classe, Filiere
from etudiants.models import Etudiant
from paiements.models import Frais, FilierePaymentPolicy, FiliereInstallmentTemplate, StudentPaymentPlan, Paiement
from revenus.models import Revenu
from depenses.models import Depense
from formateurs.models import Formateur

print("Starting financial data population...")

# 1. Clear existing data
Paiement.objects.all().delete()
StudentPaymentPlan.objects.all().delete()
FilierePaymentPolicy.objects.all().delete()
Frais.objects.all().delete()
Revenu.objects.all().delete()
Depense.objects.all().delete()

# 2. Create Frais for each class
classes = Classe.objects.all()
for cl in classes:
    # Registration fee
    Frais.objects.create(
        classe=cl,
        libelle="Frais d'inscription",
        montant=Decimal("50000.00"),
        obligatoire=True,
        date_echeance=date(2025, 9, 30)
    )
    # Tuition fee (we will use this for reference in the plan)
    Frais.objects.create(
        classe=cl,
        libelle="Frais de formation",
        montant=Decimal("450000.00"),
        obligatoire=True,
        date_echeance=date(2026, 5, 30)
    )

print(f"Created fees for {classes.count()} classes.")

# 3. Create Payment Policies for Filieres
filieres = Filiere.objects.all()
for f in filieres:
    policy = FilierePaymentPolicy.objects.create(
        filiere=f,
        four_installments_enabled=True,
        monthly_enabled=False
    )
    # Create 4 tranches
    for i in range(1, 5):
        due_date = date(2025, 10 + i if 10+i <= 12 else i-2, 25)
        if 10+i > 12: due_date = due_date.replace(year=2026)
        
        FiliereInstallmentTemplate.objects.create(
            policy=policy,
            order=i,
            label=f"Tranche {i}",
            due_date=due_date,
            amount_due=Decimal("112500.00") # 450000 / 4
        )

print(f"Created payment policies for {filieres.count()} filieres.")

# 4. Create Student Plans and Payments
students = Etudiant.objects.all()
statuses = ["SOLDE", "A_JOUR", "RETARD"]
counts = {"SOLDE": 0, "A_JOUR": 0, "RETARD": 0}

for s in students:
    if not s.filiere: continue
    
    # Create Plan
    plan = StudentPaymentPlan.objects.create(
        etudiant=s,
        filiere=s.filiere,
        policy=s.filiere.payment_policy,
        mode="FOUR_INSTALLMENTS",
        total_amount=Decimal("450000.00"),
        status="ACTIVE"
    )
    plan.generate_installments()
    
    # Determine status for this dummy student
    status = random.choice(statuses)
    counts[status] += 1
    
    # Always pay Registration
    ins_frais = Frais.objects.filter(classe__in=s.inscriptions.values_list('classe', flat=True), libelle="Frais d'inscription").first()
    if ins_frais:
        Paiement.objects.create(
            etudiant=s,
            frais=ins_frais,
            paiement_type="INSCRIPTION",
            montant_paye=ins_frais.montant,
            moyen_paiement=random.choice(["cash", "mobile_money", "virement"])
        )
    
    # Tuition payments based on status
    if status == "SOLDE":
        Paiement.objects.create(
            etudiant=s,
            paiement_type="FORMATION",
            montant_paye=Decimal("450000.00"),
            moyen_paiement="virement"
        )
    elif status == "A_JOUR":
        # Pay first 2 tranches
        Paiement.objects.create(
            etudiant=s,
            paiement_type="FORMATION",
            montant_paye=Decimal("225000.00"),
            moyen_paiement="mobile_money"
        )
    elif status == "RETARD":
        # Pay nothing for formation, or just a small part
        if random.random() > 0.5:
            Paiement.objects.create(
                etudiant=s,
                paiement_type="FORMATION",
                montant_paye=Decimal("50000.00"),
                moyen_paiement="cash"
            )

print(f"Processed payments for {len(students)} students: {counts}")

# 5. General Revenues
rev_cats = ["Subvention", "Activite", "Location", "Vente"]
for i in range(5):
    Revenu.objects.create(
        libelle=f"Revenu divers {i+1}",
        montant=Decimal(random.randint(50000, 500000)),
        categorie=random.choice(rev_cats),
        responsable="Admin",
        statut="Validé"
    )

# 6. General Expenses
exp_cats = ["Materiel", "Entretien", "Logistique", "Activites"]
trainers = list(Formateur.objects.all())
formateur_ct = ContentType.objects.get_for_model(Formateur)

for i in range(8):
    resp = random.choice(trainers) if trainers else None
    Depense.objects.create(
        libelle=f"Achat {random.choice(['craies', 'marqueurs', 'papier', 'maintenance climatisation'])} {i+1}",
        montant=Decimal(random.randint(10000, 150000)),
        categorie=random.choice(exp_cats),
        responsable_content_type=formateur_ct if resp else None,
        responsable_object_id=resp.id if resp else None,
        statut="Validée"
    )

print("Financial data population complete!")
