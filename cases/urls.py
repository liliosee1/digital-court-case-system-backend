from django.urls import path
from django.views.generic import TemplateView

from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from .schema import CourtAPISchemaGenerator
from .views import (
    APIRootAPIView,
    CaseDetailAPIView,
    CaseHistoryDetailAPIView,
    CaseHistoryListAPIView,
    CaseListCreateAPIView,
    CasePartyDetailAPIView,
    CasePartyListCreateAPIView,
    CourtroomListAPIView,
    DashboardSummaryAPIView,
    HearingDetailAPIView,
    HearingListCreateAPIView,
    JudgeListAPIView,
    LoginAPIView,
    PartyDetailAPIView,
    PartyListCreateAPIView,
    RoleListAPIView,
    UserDetailAPIView,
    UserListCreateAPIView,
)


schema_view = get_schema_view(
    title="Digital Court Case Tracking and Scheduling API",
    description="API for the Gasabo Primary Court case tracking system.",
    version="1.0.0",
    public=True,
    renderer_classes=[JSONOpenAPIRenderer],
    generator_class=CourtAPISchemaGenerator,
)


urlpatterns = [
    path("", APIRootAPIView.as_view(), name="api-root"),
    path("auth/login/", LoginAPIView.as_view(), name="api-login"),
    path("cases/", CaseListCreateAPIView.as_view(), name="case-list"),
    path("cases/<int:pk>/", CaseDetailAPIView.as_view(), name="case-detail"),
    path("parties/", PartyListCreateAPIView.as_view(), name="party-list"),
    path("parties/<int:pk>/", PartyDetailAPIView.as_view(), name="party-detail"),
    path("case-parties/", CasePartyListCreateAPIView.as_view(), name="case-party-list"),
    path("case-parties/<int:pk>/", CasePartyDetailAPIView.as_view(), name="case-party-detail"),
    path("hearings/", HearingListCreateAPIView.as_view(), name="hearing-list"),
    path("hearings/<int:pk>/", HearingDetailAPIView.as_view(), name="hearing-detail"),
    path("case-history/", CaseHistoryListAPIView.as_view(), name="case-history-list"),
    path("case-history/<int:pk>/", CaseHistoryDetailAPIView.as_view(), name="case-history-detail"),
    path("courtrooms/", CourtroomListAPIView.as_view(), name="courtroom-list"),
    path("judges/", JudgeListAPIView.as_view(), name="judge-list"),
    path("roles/", RoleListAPIView.as_view(), name="role-list"),
    path("users/", UserListCreateAPIView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailAPIView.as_view(), name="user-detail"),
    path("dashboard/summary/", DashboardSummaryAPIView.as_view(), name="dashboard-summary"),
    path("schema/", schema_view, name="openapi-schema"),
    path(
        "docs/",
        TemplateView.as_view(template_name="cases/api_docs.html"),
        name="api-docs",
    ),
]
