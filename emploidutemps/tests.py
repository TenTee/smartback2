from django.test import TestCase
from django.core.exceptions import ValidationError
from datetime import time
from formateurs.models import Formateur
from modules.models import Module
from academique.models import Filiere, Departement, UniversiteTutelle
from emploidutemps.models import EmploiDuTemps

class EmploiDuTempsTests(TestCase):
    def setUp(self):
        # Création des structures parentes
        self.tutelle = UniversiteTutelle.objects.create(nom="Tutelle Test")
        self.dept = Departement.objects.create(nom="Dept Test", universite_tutelle=self.tutelle)

        # Création d’un formateur
        self.formateur = Formateur.objects.create(nom="M. Dupont")

        # Création d’un module
        self.module = Module.objects.create(nom="Mathématiques")

        # Création de deux filières
        self.filiereA = Filiere.objects.create(nom="Filiere A", departement=self.dept)
        self.filiereB = Filiere.objects.create(nom="Filiere B", departement=self.dept)

    def test_seance_creation(self):
        """Créer une séance dans Filiere A."""
        seance = EmploiDuTemps.objects.create(
            filiere=self.filiereA,
            module=self.module,
            formateur=self.formateur,
            jour="Lundi",
            heure_debut=time(9, 0),
            heure_fin=time(11, 0),
            salle="Salle 101"
        )

        # Vérifier que la séance existe dans Filiere A
        self.assertTrue(
            EmploiDuTemps.objects.filter(filiere=self.filiereA, module=self.module).exists()
        )

    def test_pause_non_autorisee(self):
        """Vérifier qu'une séance pendant la pause (12h-13h) est refusée."""
        with self.assertRaises(ValidationError):
            seance = EmploiDuTemps(
                filiere=self.filiereA,
                module=self.module,
                formateur=self.formateur,
                jour="Mardi",
                heure_debut=time(12, 0),
                heure_fin=time(12, 30),
                salle="Salle 102"
            )
            seance.clean()  # déclenche la validation

    def test_conflit_de_salle(self):
        """Vérifier qu'une salle ne peut pas accueillir deux séances en même temps."""
        EmploiDuTemps.objects.create(
            filiere=self.filiereA,
            module=self.module,
            formateur=self.formateur,
            jour="Mercredi",
            heure_debut=time(10, 0),
            heure_fin=time(11, 0),
            salle="Salle 103"
        )

        # Tentative de créer une autre séance dans la même salle et créneau
        with self.assertRaises(ValidationError):
            seance_conflict = EmploiDuTemps(
                filiere=self.filiereB,
                module=self.module,
                formateur=self.formateur,
                jour="Mercredi",
                heure_debut=time(10, 30),
                heure_fin=time(11, 30),
                salle="Salle 103"
            )
            seance_conflict.clean()