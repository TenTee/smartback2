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
    CourseViewSet,
    CycleViewSet,
    DomaineViewSet,
    EvaluationViewSet,
    FaculteViewSet,
    FiliereViewSet,
    FraisViewSet,
    LevelViewSet,
    SemestreViewSet,
    SpecialiteViewSet,
    PreInscriptionViewSet,
)

router = DefaultRouter()
router.register(r"facultes", FaculteViewSet, basename="academique-faculte")
router.register(r"domaines", DomaineViewSet, basename="academique-domaine")
router.register(r"filieres", FiliereViewSet, basename="academique-filiere")
router.register(r"specialites", SpecialiteViewSet, basename="academique-specialite")
router.register(r"cycles", CycleViewSet, basename="academique-cycle")
router.register(r"levels", LevelViewSet, basename="academique-level")
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

urlpatterns = [
    path("", include(router.urls)),
]
