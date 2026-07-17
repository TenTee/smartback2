from django.urls import path

from .views import (
    ClassePaymentScheduleDetailView,
    ClassePaymentScheduleListCreateView,
    FilierePaymentPolicyDetailView,
    FilierePaymentPolicyListCreateView,
    FinancialDashboardView,
    MePaiementSummary,
    PaiementAggregated,
    PaiementDetail,
    PaiementListCreate,
    PaymentAlertListView,
    StudentPaymentPlanDetailView,
    StudentPaymentPlanListCreateView,
    StudentResolvedScheduleView,
    StudentScheduleOverrideView,
)

urlpatterns = [
    path("paiements/me/", MePaiementSummary.as_view(), name="paiement-me"),
    path("paiements/dashboard/", FinancialDashboardView.as_view(), name="financial-dashboard"),
    path("paiements/", PaiementListCreate.as_view(), name="paiement-list"),
    path("paiements/<int:pk>/", PaiementDetail.as_view(), name="paiement-detail"),
    path("paiements/aggregated/", PaiementAggregated.as_view(), name="paiement-aggregated"),
    path("paiements/configurations/", FilierePaymentPolicyListCreateView.as_view(), name="paiement-policy-list"),
    path("paiements/configurations/<int:pk>/", FilierePaymentPolicyDetailView.as_view(), name="paiement-policy-detail"),
    path("paiements/plans/", StudentPaymentPlanListCreateView.as_view(), name="student-payment-plan-list"),
    path("paiements/plans/<int:pk>/", StudentPaymentPlanDetailView.as_view(), name="student-payment-plan-detail"),
    path("paiements/alerts/", PaymentAlertListView.as_view(), name="payment-alert-list"),
    path("paiements/class-schedules/", ClassePaymentScheduleListCreateView.as_view(), name="class-schedule-list"),
    path("paiements/class-schedules/<int:pk>/", ClassePaymentScheduleDetailView.as_view(), name="class-schedule-detail"),
    path("paiements/student-schedule/<int:etudiant_id>/", StudentResolvedScheduleView.as_view(), name="student-resolved-schedule"),
    path("paiements/student-schedule/<int:etudiant_id>/override/", StudentScheduleOverrideView.as_view(), name="student-schedule-override"),
]
