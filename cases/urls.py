from django.urls import path

from .views import CaseListAPIView


urlpatterns = [
    path("cases/", CaseListAPIView.as_view(), name="case-list"),
]
