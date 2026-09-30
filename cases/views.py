from datetime import datetime

from django.contrib.auth.hashers import (
    UNUSABLE_PASSWORD_PREFIX,
    check_password,
    identify_hasher,
    make_password,
)
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from django.utils.crypto import constant_time_compare

from .authentication import BearerTokenAuthentication, TOKEN_SALT
from .models import Case, CaseHistory, CaseParty, Courtroom, Hearing, Party, Role, User
from .permissions import (
    CaseAccessPermission,
    IsAdministratorOnly,
    IsAuthenticatedUser,
    IsCourtStaffOrReadOnly,
)
from .serializers import (
    CaseHistorySerializer,
    CasePartySerializer,
    CaseSerializer,
    CourtroomSerializer,
    HearingSerializer,
    LoginSerializer,
    PartySerializer,
    RoleSerializer,
    UserManagementSerializer,
    UserSerializer,
)


_DUMMY_PASSWORD_HASH = make_password("not-a-real-user-password")


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This operation conflicts with existing court records."
    default_code = "conflict"


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def positive_integer_filter(request, name):
    value = request.query_params.get(name)
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Enter a positive integer."})
    if result < 1:
        raise ValidationError({name: "Enter a positive integer."})
    return result


def date_filter(request, name):
    value = request.query_params.get(name)
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError({name: "Use the YYYY-MM-DD date format."})


def add_case_history(case, user, action, description=""):
    CaseHistory.objects.create(
        case=case,
        user=user,
        action=action,
        description=description,
        created_at=timezone.now(),
    )


class LoginAPIView(APIView):
    """Verify credentials and issue an eight-hour signed API token."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.select_related("role").get(email__iexact=email)
        except User.DoesNotExist:
            check_password(password, _DUMMY_PASSWORD_HASH)
            user = None

        password_is_valid = False
        if user is not None:
            stored_value = user.password_hash
            if stored_value.startswith(UNUSABLE_PASSWORD_PREFIX):
                password_is_valid = False
            else:
                try:
                    identify_hasher(stored_value)
                except ValueError:
                    # Compatibility for legacy rows; successful logins upgrade them.
                    check_password(password, _DUMMY_PASSWORD_HASH)
                    password_is_valid = constant_time_compare(password, stored_value)
                    if password_is_valid:
                        user.password_hash = make_password(password)
                        user.save(update_fields=["password_hash"])
                else:
                    password_is_valid = check_password(password, stored_value)

        if user is None or not password_is_valid:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token = signing.dumps({"user_id": user.pk}, salt=TOKEN_SALT, compress=True)
        return Response(
            {"token": token, "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class APIRootAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({
            "login": "/api/auth/login/",
            "cases": "/api/cases/",
            "parties": "/api/parties/",
            "case_parties": "/api/case-parties/",
            "hearings": "/api/hearings/",
            "case_history": "/api/case-history/",
            "courtrooms": "/api/courtrooms/",
            "judges": "/api/judges/",
            "roles": "/api/roles/",
            "users": "/api/users/",
            "dashboard": "/api/dashboard/summary/",
            "schema": "/api/schema/",
            "documentation": "/api/docs/",
        })


class ProtectedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticatedUser]


class CaseListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CaseSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [CaseAccessPermission]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Case.objects.select_related("assigned_judge", "created_by").order_by("id")
        params = self.request.query_params
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(case_number__icontains=search)
                | Q(title__icontains=search)
                | Q(description__icontains=search)
            )
        if params.get("status"):
            queryset = queryset.filter(status__iexact=params["status"].strip())
        if params.get("case_type"):
            queryset = queryset.filter(case_type__iexact=params["case_type"].strip())
        judge_id = positive_integer_filter(self.request, "assigned_judge")
        if judge_id:
            queryset = queryset.filter(assigned_judge_id=judge_id)
        filed_after = date_filter(self.request, "filed_after")
        filed_before = date_filter(self.request, "filed_before")
        if filed_after:
            queryset = queryset.filter(filing_date__gte=filed_after)
        if filed_before:
            queryset = queryset.filter(filing_date__lte=filed_before)
        if filed_after and filed_before and filed_after > filed_before:
            raise ValidationError({"filed_after": "Must be on or before filed_before."})
        return queryset

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        now = timezone.now()
        case = serializer.save(
            created_by=self.request.user, created_at=now, updated_at=now
        )
        add_case_history(
            case,
            self.request.user,
            "Case created",
            f"Case {case.case_number} was created.",
        )


class CaseDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CaseSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [CaseAccessPermission]

    def get_queryset(self):
        return Case.objects.select_related("assigned_judge", "created_by")

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        case = serializer.save(updated_at=timezone.now())
        changed_fields = ", ".join(serializer.validated_data.keys()) or "case details"
        add_case_history(
            case,
            self.request.user,
            "Case updated",
            f"Updated fields: {changed_fields}.",
        )

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            case = self.get_object()
            if (
                Hearing.objects.filter(case_id=case.pk).exists()
                or CaseParty.objects.filter(case_id=case.pk).exists()
            ):
                raise Conflict(
                    "This case has hearings or linked parties and cannot be deleted. "
                    "Preserve its hearing and party records by changing its status instead."
                )
            return super().destroy(request, *args, **kwargs)


class PartyListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PartySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Party.objects.all().order_by("id")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        party_type = self.request.query_params.get("party_type")
        if party_type:
            queryset = queryset.filter(party_type__iexact=party_type.strip())
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_at=timezone.now())


class PartyDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        party = serializer.save()
        linked_cases = Case.objects.filter(caseparty__party=party)
        for case in linked_cases:
            add_case_history(
                case,
                self.request.user,
                "Party updated",
                f"Contact details for {party.full_name} were updated.",
            )

    def perform_destroy(self, instance):
        if CaseParty.objects.filter(party_id=instance.pk).exists():
            raise Conflict(
                "Unlink this party from its cases before deleting the party record."
            )
        instance.delete()


class CasePartyListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CasePartySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().create(request, *args, **kwargs)

    def get_queryset(self):
        queryset = CaseParty.objects.select_related("case", "party").order_by("id")
        case_id = positive_integer_filter(self.request, "case")
        party_id = positive_integer_filter(self.request, "party")
        if case_id:
            queryset = queryset.filter(case_id=case_id)
        if party_id:
            queryset = queryset.filter(party_id=party_id)
        return queryset

    def perform_create(self, serializer):
        link = serializer.save()
        add_case_history(
            link.case,
            self.request.user,
            "Party linked",
            f"{link.party.full_name} was linked to the case.",
        )


class CasePartyDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CaseParty.objects.select_related("case", "party")
    serializer_class = CasePartySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        old_case = serializer.instance.case
        old_party = serializer.instance.party
        link = serializer.save()
        if old_case.pk != link.case.pk:
            add_case_history(
                old_case,
                self.request.user,
                "Party unlinked",
                f"{old_party.full_name} was moved to another case.",
            )
        add_case_history(
            link.case,
            self.request.user,
            "Party link updated",
            f"{link.party.full_name} case link was updated.",
        )

    def perform_destroy(self, instance):
        add_case_history(
            instance.case,
            self.request.user,
            "Party unlinked",
            f"{instance.party.full_name} was unlinked from the case.",
        )
        instance.delete()


class HearingListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = HearingSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Hearing.objects.select_related(
            "case", "judge", "courtroom", "created_by"
        ).order_by("hearing_date", "hearing_time", "id")
        if self.request.user.role.name.casefold() == "judge":
            queryset = queryset.filter(judge_id=self.request.user.pk)
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status__iexact=params["status"].strip())
        for parameter, field in (
            ("case", "case_id"),
            ("judge", "judge_id"),
            ("courtroom", "courtroom_id"),
        ):
            value = positive_integer_filter(self.request, parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        date_from = date_filter(self.request, "date_from")
        date_to = date_filter(self.request, "date_to")
        if date_from:
            queryset = queryset.filter(hearing_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(hearing_date__lte=date_to)
        if date_from and date_to and date_from > date_to:
            raise ValidationError({"date_from": "Must be on or before date_to."})
        return queryset

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        now = timezone.now()
        hearing = serializer.save(
            created_by=self.request.user, created_at=now, updated_at=now
        )
        add_case_history(
            hearing.case,
            self.request.user,
            "Hearing scheduled",
            f"Hearing {hearing.pk} scheduled for {hearing.hearing_date} at {hearing.hearing_time}.",
        )

    def perform_update(self, serializer):
        old_case = serializer.instance.case
        hearing = serializer.save(updated_at=timezone.now())
        if old_case.pk != hearing.case.pk:
            add_case_history(
                old_case,
                self.request.user,
                "Hearing moved",
                f"Hearing {hearing.pk} was moved to another case.",
            )
        add_case_history(
            hearing.case,
            self.request.user,
            "Hearing updated",
            f"Hearing {hearing.pk} details were updated.",
        )


class HearingDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Hearing.objects.select_related("case", "judge", "courtroom", "created_by")
    serializer_class = HearingSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsCourtStaffOrReadOnly]

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        old_case = serializer.instance.case
        hearing = serializer.save(updated_at=timezone.now())
        if old_case.pk != hearing.case.pk:
            add_case_history(
                old_case,
                self.request.user,
                "Hearing moved",
                f"Hearing {hearing.pk} was moved to another case.",
            )
        add_case_history(
            hearing.case,
            self.request.user,
            "Hearing updated",
            f"Hearing {hearing.pk} details were updated.",
        )

    def perform_destroy(self, instance):
        add_case_history(
            instance.case,
            self.request.user,
            "Hearing deleted",
            f"Hearing {instance.pk} was deleted.",
        )
        instance.delete()


class CaseHistoryListAPIView(generics.ListAPIView):
    serializer_class = CaseHistorySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticatedUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = CaseHistory.objects.select_related("case", "user").order_by("-created_at", "-id")
        case_id = positive_integer_filter(self.request, "case")
        user_id = positive_integer_filter(self.request, "user")
        if case_id:
            queryset = queryset.filter(case_id=case_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if self.request.query_params.get("action"):
            queryset = queryset.filter(action__icontains=self.request.query_params["action"].strip())
        return queryset


class CaseHistoryDetailAPIView(generics.RetrieveAPIView):
    queryset = CaseHistory.objects.select_related("case", "user")
    serializer_class = CaseHistorySerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticatedUser]


class CourtroomListAPIView(generics.ListAPIView):
    queryset = Courtroom.objects.all().order_by("name")
    serializer_class = CourtroomSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticatedUser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Courtroom.objects.all().order_by("name")
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status__iexact=self.request.query_params["status"])
        return queryset


class JudgeListAPIView(generics.ListAPIView):
    queryset = User.objects.select_related("role").filter(role__name__iexact="Judge").order_by("full_name")
    serializer_class = UserSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticatedUser]
    pagination_class = StandardResultsSetPagination


class RoleListAPIView(generics.ListAPIView):
    queryset = Role.objects.all().order_by("id")
    serializer_class = RoleSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAdministratorOnly]


class UserListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = UserManagementSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAdministratorOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = User.objects.select_related("role").order_by("full_name", "id")
        role_id = positive_integer_filter(self.request, "role")
        if role_id:
            queryset = queryset.filter(role_id=role_id)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(email__icontains=search)
            )
        return queryset

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().create(request, *args, **kwargs)


class UserDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.select_related("role")
    serializer_class = UserManagementSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAdministratorOnly]

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise Conflict("You cannot delete your own administrator account.")
        if (
            instance.role.name.casefold() == "administrator"
            and User.objects.filter(role__name__iexact="Administrator").count() <= 1
        ):
            raise Conflict("The last Administrator account cannot be deleted.")
        has_related_records = (
            Case.objects.filter(Q(created_by=instance) | Q(assigned_judge=instance)).exists()
            or Hearing.objects.filter(
                Q(judge=instance) | Q(created_by=instance)
            ).exists()
            or CaseHistory.objects.filter(user=instance).exists()
        )
        if has_related_records:
            raise Conflict(
                "This user is referenced by court records and cannot be deleted."
            )
        instance.delete()


class DashboardSummaryAPIView(ProtectedAPIView):
    def get(self, request):
        cases = Case.objects.all()
        hearings = Hearing.objects.all()
        if request.user.role.name.casefold() == "judge":
            cases = cases.filter(assigned_judge_id=request.user.pk)
            hearings = hearings.filter(judge_id=request.user.pk)

        return Response({
            "cases": {
                "total": cases.count(),
                "by_status": list(
                    cases.values("status").annotate(count=Count("id")).order_by("status")
                ),
                "by_type": list(
                    cases.values("case_type").annotate(count=Count("id")).order_by("case_type")
                ),
            },
            "hearings": {
                "total": hearings.count(),
                "upcoming": hearings.filter(
                    hearing_date__gte=timezone.localdate(), status__iexact="Scheduled"
                ).count(),
                "by_status": list(
                    hearings.values("status").annotate(count=Count("id")).order_by("status")
                ),
            },
            "parties": Party.objects.count(),
            "case_party_links": CaseParty.objects.count(),
        })
