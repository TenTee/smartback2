from django.test import TestCase
from django.core.exceptions import ValidationError
from datetime import time
from formateurs.models import Formateur
from modules.models import Module
from formations.models import Formation
from emploidutemps.models import EmploiDuTemps

class EmploiDuTempsTests(TestCase):
    def setUp(self):
        # Création d’un formateur
        self.formateur = Formateur.objects.create(nom="M. Dupont")

        # Création d’un module
        self.module = Module.objects.create(nom="Mathématiques")

        # Création de deux formations qui partagent le même module (tronc commun)
        self.formationA = Formation.objects.create(intitule="Formation A")
        self.formationB = Formation.objects.create(intitule="Formation B")

        # Associer le module aux deux formations
        self.formationA.modules.add(self.module)
        self.formationB.modules.add(self.module)

    def test_propagation_tronc_commun(self):
        """Créer une séance dans Formation A doit aussi créer la même séance dans Formation B."""
        seance = EmploiDuTemps.objects.create(
            formation=self.formationA,
            module=self.module,
            formateur=self.formateur,
            jour="Lundi",
            heure_debut=time(9, 0),
            heure_fin=time(11, 0),
            salle="Salle 101"
        )

        # Vérifier que la séance existe dans Formation A
        self.assertTrue(
            EmploiDuTemps.objects.filter(formation=self.formationA, module=self.module).exists()
        )

        # Vérifier que la séance a été propagée dans Formation B
        self.assertTrue(
            EmploiDuTemps.objects.filter(formation=self.formationB, module=self.module).exists()
        )

    def test_pause_non_autorisee(self):
        """Vérifier qu'une séance pendant la pause (12h-13h) est refusée."""
        with self.assertRaises(ValidationError):
            seance = EmploiDuTemps(
                formation=self.formationA,
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
            formation=self.formationA,
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
                formation=self.formationB,
                module=self.module,
                formateur=self.formateur,
                jour="Mercredi",
                heure_debut=time(10, 30),
                heure_fin=time(11, 30),
                salle="Salle 103"
            )
            seance_conflict.clean()