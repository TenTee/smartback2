from django.urls import path

from .views import (
    FilierePaymentPolicyDetailView,
    FilierePaymentPolicyListCreateView,
    PaiementAggregated,
    PaiementDetail,
    PaiementListCreate,
    PaymentAlertListView,
    StudentPaymentPlanDetailView,
    StudentPaymentPlanListCreateView,
)

urlpatterns = [
    path("paiements/", PaiementListCreate.as_view(), name="paiement-list"),
    path("paiements/<int:pk>/", PaiementDetail.as_view(), name="paiement-detail"),
    path("paiements/aggregated/", PaiementAggregated.as_view(), name="paiement-aggregated"),
    path("paiements/configurations/", FilierePaymentPolicyListCreateView.as_view(), name="paiement-policy-list"),
    path("paiements/configurations/<int:pk>/", FilierePaymentPolicyDetailView.as_view(), name="paiement-policy-detail"),
    path("paiements/plans/", StudentPaymentPlanListCreateView.as_view(), name="student-payment-plan-list"),
    path("paiements/plans/<int:pk>/", StudentPaymentPlanDetailView.as_view(), name="student-payment-plan-detail"),
    path("paiements/alerts/", PaymentAlertListView.as_view(), name="payment-alert-list"),
]
