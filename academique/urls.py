from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcademicEmploiDuTempsViewSet,
    AcademicInscriptionViewSet,
    AcademicNoteViewSet,
    AcademicPaiementViewSet,
    AffectationViewSet,
    AnneeAcademiqueViewSet,
    ClasseViewSet,
    ConfigurationEtablissementViewSet,
    CourseViewSet,
    CycleViewSet,
    CycleGlobalViewSet,
    DepartementViewSet,
    EvaluationViewSet,
    FiliereViewSet,
    FraisViewSet,
    LevelViewSet,
    ParametresGlobauxViewSet,
    PreInscriptionViewSet,
    SemestreViewSet,
    UniversiteTutelleViewSet,
)

router = DefaultRouter()
router.register(r"parametres-globaux", ParametresGlobauxViewSet, basename="academique-parametres-globaux")
router.register(r"configuration-etablissement", ConfigurationEtablissementViewSet, basename="academique-configuration-etablissement")
router.register(r"universites-tutelles", UniversiteTutelleViewSet, basename="academique-universite-tutelle")
router.register(r"departements", DepartementViewSet, basename="academique-departement")
router.register(r"filieres", FiliereViewSet, basename="academique-filiere")
router.register(r"cycles-globaux", CycleGlobalViewSet, basename="academique-cycle-global")
router.register(r"cycles", CycleViewSet, basename="academique-cycle")
router.register(r"niveaux", LevelViewSet, basename="academique-niveau")
router.register(r"courses", CourseViewSet, basename="academique-course")
router.register(r"annees-academiques", AnneeAcademiqueViewSet, basename="academique-annee")
router.register(r"classes", ClasseViewSet, basename="academique-classe")
router.register(r"semestres", SemestreViewSet, basename="academique-semestre")
router.register(r"evaluations", EvaluationViewSet, basename="academique-evaluation")
router.register(r"affectations", AffectationViewSet, basename="academique-affectation")
router.register(r"inscriptions", AcademicInscriptionViewSet, basename="academique-inscription")
router.register(r"notes", AcademicNoteViewSet, basename="academique-note")
router.register(r"frais", FraisViewSet, basename="academique-frais")
router.register(r"paiements", AcademicPaiementViewSet, basename="academique-paiement")
router.register(r"emplois-du-temps", AcademicEmploiDuTempsViewSet, basename="academique-emploi")
router.register(r"pre-inscriptions", PreInscriptionViewSet, basename="academique-preinscription")

# Alias de compatibilité
router.register(r"facultes", UniversiteTutelleViewSet, basename="academique-faculte")
router.register(r"domaines", DepartementViewSet, basename="academique-domaine")
router.register(r"levels", LevelViewSet, basename="academique-level")

urlpatterns = [
    path("", include(router.urls)),
]
