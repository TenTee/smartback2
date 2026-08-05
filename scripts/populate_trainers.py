import random
from formateurs.models import Formateur
from academique.models import Classe, Affectation
from modules.models import Module

print("Starting trainer population...")

# 1. Clear existing trainers and affectations
Affectation.objects.all().delete()
Formateur.objects.all().delete()

first_names = ["Marc", "Alice", "Robert", "Sandrine", "Kevin", "Béatrice", "Patrice", "Hélène", "Gérard", "Yasmine"]
last_names = ["Kone", "Toure", "Diop", "Mballa", "Kamga", "Ngo", "Sow", "Keita", "Diallo", "Mensah"]

trainers = []
for i in range(12):
    nom = f"{random.choice(last_names)} {random.choice(first_names)}"
    email = f"trainer.{i}@smartcampus.test"
    t = Formateur.objects.create(
        nom=nom,
        email=email,
        contact=f"6{random.randint(50, 99)}{random.randint(100000, 999999)}",
        salaire=random.randint(300000, 800000)
    )
    trainers.append(t)

print(f"Created {len(trainers)} trainers.")

# 2. Assign trainers to each module of each class
classes = Classe.objects.all()
count = 0
for cl in classes:
    modules = cl.modules.all()
    for m in modules:
        # Randomly assign a trainer
        trainer = random.choice(trainers)
        Affectation.objects.get_or_create(
            enseignant=trainer,
            module=m,
            classe=cl
        )
        count += 1

print(f"Created {count} affectations (trainer assignments).")
