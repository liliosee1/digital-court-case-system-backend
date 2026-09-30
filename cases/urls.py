from django.urls import path

from .views import CaseDetailAPIView, CaseListCreateAPIView


urlpatterns = [
    path("cases/", CaseListCreateAPIView.as_view(), name="case-list"),
    path("cases/<int:pk>/", CaseDetailAPIView.as_view(), name="case-detail"),
]
