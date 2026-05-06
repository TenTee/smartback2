import os
import random
from django.utils import timezone
from academique.models import (
    AnneeAcademique, Semestre, UniversiteTutelle, Departement, Filiere, 
    CycleGlobal, Cycle, Niveau, Classe, Evaluation, CourseAssignment
)
from modules.models import Module
from etudiants.models import Etudiant, Inscription
from notes.models import Note

print("Clearing existing data for a clean test state...")
Note.objects.all().delete()
Evaluation.objects.all().delete()
Inscription.objects.all().delete()
Etudiant.objects.all().delete()
CourseAssignment.objects.all().delete()
Classe.objects.all().delete()
# We keep UniversiteTutelle and Departement but clear Filieres to avoid prefix clashes
Filiere.objects.all().delete()
Module.objects.all().delete()

print("Starting data population...")

# 1. Academic Year
year_libelle = "2025-2026"
annee, _ = AnneeAcademique.objects.get_or_create(
    libelle=year_libelle,
    defaults={"est_active": True}
)

# 2. Semesters
s1, _ = Semestre.objects.get_or_create(
    annee_academique=annee, ordre=1,
    defaults={"nom": "Semestre 1"}
)
s2, _ = Semestre.objects.get_or_create(
    annee_academique=annee, ordre=2,
    defaults={"nom": "Semestre 2"}
)

# 3. Hierarchy
uni, _ = UniversiteTutelle.objects.get_or_create(nom="Université de SmartCampus")
dept, _ = Departement.objects.get_or_create(universite_tutelle=uni, nom="Faculté des Sciences et Technologies")

# Use distinct prefixes
filieres_data = [
    ("Informatique de Gestion", "INF"), 
    ("Management des Entreprises", "MGT"), 
    ("Communication Visuelle", "COM"), 
    ("Marketing Digital", "MRK")
]
filieres = []
for f_nom, prefix in filieres_data:
    f, _ = Filiere.objects.get_or_create(departement=dept, nom=f_nom)
    filieres.append((f, prefix))

# 4. Cycles
cg_bts, _ = CycleGlobal.objects.get_or_create(nom="BTS")

# 5. Modules (25 modules)
module_names = [
    "Algorithmique Appliquée", "Bases de Données SQL", "Développement Mobile", "Réseaux de Neurones", "Sécurité Informatique",
    "Comptabilité de Gestion", "Marketing Stratégique", "Droit du Travail", "Économie Monétaire", "Analyse Financière",
    "Psychologie de la Comm", "Graphisme & Design", "Audiovisuel", "Relations Publiques", "Événementiel",
    "Big Data Marketing", "Growth Hacking", "SEO & SEM", "E-réputation", "Droit du Numérique",
    "Anglais des Affaires", "Gestion de Projet Agile", "Mathématiques Discrètes", "Statistiques", "Entrepreneuriat"
]
modules = []
for m_nom in module_names:
    m, _ = Module.objects.get_or_create(nom=m_nom, defaults={"coefficient": random.randint(2, 5)})
    modules.append(m)

# 6. Students Names
first_names = ["Jean", "Marie", "Paul", "Sophie", "Lucas", "Emma", "Thomas", "Julie", "Nicolas", "Chloé", "Adrien", "Léa", "Hugo", "Manon", "Arthur"]
last_names = ["Dupont", "Durand", "Lefebvre", "Moreau", "Petit", "Roux", "Vincent", "Girard", "Andre", "Mercier", "Blanc", "Guerin", "Boyer", "Garnier", "Chevalier"]

# 7. Create Structure and Inscribe Students
student_total = 0
for f, prefix in filieres:
    cyc, _ = Cycle.objects.get_or_create(filiere=f, type_cycle=cg_bts, defaults={"nom": "BTS"})
    
    for i in range(1, 3): # 2 Levels
        niv, _ = Niveau.objects.get_or_create(cycle=cyc, nom=f"Niveau {i}")
        
        classe, _ = Classe.objects.get_or_create(
            filiere=f, cycle=cyc, niveau=niv, annee_academique=annee,
            defaults={"nom": f"{f.nom} - {niv.nom}"}
        )

        # Assign 6 modules per class
        selected_modules = random.sample(modules, 6)
        for m in selected_modules:
            classe.modules.add(m)
            CourseAssignment.objects.get_or_create(filiere=f, cycle=cyc, niveau=niv, module=m)
            Evaluation.objects.get_or_create(classe=classe, module=m, type_evaluation="CC", libelle=f"CC1 {m.nom}", defaults={"coefficient": 1})

        # Inscribe 8 students per class (8 * 2 levels * 4 filieres = 64 students)
        for j in range(8):
            nom = random.choice(last_names)
            prenom = random.choice(first_names)
            email = f"{prenom.lower()}.{nom.lower()}.{f.id}.{niv.id}.{j}@campus.test"
            
            etudiant = Etudiant.objects.create(
                email=email,
                nom=f"{nom} {prenom}",
                contact=f"6{random.randint(50, 99)}{random.randint(100000, 999999)}",
                filiere=f,
                statut="Inscrit"
            )
            
            Inscription.objects.create(
                etudiant=etudiant,
                classe=classe,
                niveau=niv,
                annee_academique=year_libelle,
                annee_academique_ref=annee
            )
            student_total += 1

print(f"Population complete. Created {student_total} students across {len(filieres)} filières.")
