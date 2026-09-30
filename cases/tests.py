import unittest
import sys
from datetime import date, time
from unittest.mock import Mock, patch

from django.contrib.auth.hashers import (
    check_password,
    make_password as django_make_password,
)
from django.core import signing
from django.core.signing import SignatureExpired
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import HttpResponse
from rest_framework.exceptions import AuthenticationFailed

from .authentication import BearerTokenAuthentication, TOKEN_SALT
from .management.commands.hash_legacy_passwords import password_is_already_hashed
from .models import Case, Courtroom, Hearing, Role, User
from .permissions import (
    CaseAccessPermission,
    IsAdministrator,
    IsCourtClerk,
    IsJudge,
)
from .views import CaseListCreateAPIView, LoginAPIView
from .serializers import HearingSerializer, UserManagementSerializer
from court_system.middleware import CORSMiddleware


def make_test_user(role_name, *, password_hash="legacy-test-password", user_id=1):
    role_id = {"Administrator": 1, "Court Clerk": 2, "Judge": 3}[role_name]
    role = Role(id=role_id, name=role_name)
    return User(
        id=user_id,
        full_name="Test User",
        email="test@example.invalid",
        password_hash=password_hash,
        role=role,
    )


class LoginAPITests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.queryset = Mock()
        self.manager_patch = patch.object(
            User.objects, "select_related", return_value=self.queryset
        )
        self.manager_patch.start()
        self.addCleanup(self.manager_patch.stop)

    def post_login(self, data):
        request = self.factory.post("/api/auth/login/", data, format="json")
        return LoginAPIView.as_view()(request)

    def test_legacy_password_login_hashes_value_and_returns_safe_user(self):
        user = make_test_user("Administrator")
        self.queryset.get.return_value = user

        with (
            patch("cases.views.check_password", return_value=False),
            patch("cases.views.make_password", return_value="encoded-test-hash"),
            patch.object(user, "save") as save_user,
        ):
            response = self.post_login(
                {"email": user.email, "password": "legacy-test-password"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.password_hash, "encoded-test-hash")
        save_user.assert_called_once_with(update_fields=["password_hash"])
        self.assertNotIn("password_hash", response.data)
        self.assertNotIn("password_hash", response.data["user"])
        self.assertEqual(response.data["user"]["role"], "Administrator")
        token_data = signing.loads(response.data["token"], salt=TOKEN_SALT)
        self.assertEqual(token_data, {"user_id": user.pk})

    def test_django_password_hash_login_does_not_rewrite_password(self):
        password = "already-hashed-test-password"
        user = make_test_user(
            "Court Clerk", password_hash=django_make_password(password)
        )
        self.queryset.get.return_value = user

        with patch.object(user, "save") as save_user:
            response = self.post_login({"email": user.email, "password": password})

        self.assertEqual(response.status_code, 200)
        save_user.assert_not_called()

    def test_wrong_password_is_rejected(self):
        user = make_test_user("Judge")
        self.queryset.get.return_value = user

        with patch("cases.views.check_password", return_value=False):
            response = self.post_login(
                {"email": user.email, "password": "incorrect-password"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Invalid email or password.")

    def test_unknown_email_is_rejected(self):
        self.queryset.get.side_effect = User.DoesNotExist
        with patch("cases.views.check_password", return_value=False):
            response = self.post_login(
                {"email": "missing@example.invalid", "password": "any-password"}
            )
        self.assertEqual(response.status_code, 401)

    def test_required_login_fields_are_validated(self):
        response = self.post_login({"email": "test@example.invalid"})
        self.assertEqual(response.status_code, 400)


class BearerAuthenticationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_test_user("Judge")
        self.queryset = Mock()
        self.queryset.get.return_value = self.user
        self.manager_patch = patch.object(
            User.objects, "select_related", return_value=self.queryset
        )
        self.manager_patch.start()
        self.addCleanup(self.manager_patch.stop)

    def test_valid_bearer_token_authenticates_user(self):
        token = signing.dumps({"user_id": self.user.pk}, salt=TOKEN_SALT)
        request = self.factory.get("/api/cases/", HTTP_AUTHORIZATION=f"Bearer {token}")

        authenticated_user, token_data = BearerTokenAuthentication().authenticate(
            request
        )

        self.assertEqual(authenticated_user.pk, self.user.pk)
        self.assertEqual(token_data, {"user_id": self.user.pk})

    def test_expired_token_is_rejected(self):
        request = self.factory.get(
            "/api/cases/", HTTP_AUTHORIZATION="Bearer expired-token"
        )
        with patch(
            "cases.authentication.signing.loads", side_effect=SignatureExpired
        ):
            with self.assertRaises(AuthenticationFailed):
                BearerTokenAuthentication().authenticate(request)

    def test_missing_token_does_not_authenticate(self):
        request = self.factory.get("/api/cases/")
        self.assertIsNone(BearerTokenAuthentication().authenticate(request))

    def test_cases_endpoint_rejects_anonymous_request(self):
        response = CaseListCreateAPIView.as_view()(self.factory.get("/api/cases/"))
        self.assertEqual(response.status_code, 401)


class RolePermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.permission = CaseAccessPermission()
        self.users = {
            role: make_test_user(role, user_id=user_id)
            for user_id, role in enumerate(
                ("Administrator", "Court Clerk", "Judge"), start=1
            )
        }

    def allowed(self, role, method):
        request = getattr(self.factory, method.lower())("/api/cases/")
        request.user = self.users[role]
        return self.permission.has_permission(request, view=None)

    def test_named_role_permissions_match_expected_roles(self):
        permissions = {
            "Administrator": IsAdministrator(),
            "Court Clerk": IsCourtClerk(),
            "Judge": IsJudge(),
        }
        for expected_role, permission in permissions.items():
            for actual_role, user in self.users.items():
                request = self.factory.get("/api/cases/")
                request.user = user
                self.assertEqual(
                    permission.has_permission(request, view=None),
                    actual_role == expected_role,
                )

    def test_cases_role_access_matrix(self):
        expected = {
            "Administrator": {"GET": True, "POST": True, "PATCH": True, "DELETE": True},
            "Court Clerk": {"GET": True, "POST": True, "PATCH": True, "DELETE": False},
            "Judge": {"GET": True, "POST": False, "PATCH": False, "DELETE": False},
        }
        for role, methods in expected.items():
            for method, is_allowed in methods.items():
                with self.subTest(role=role, method=method):
                    self.assertEqual(self.allowed(role, method), is_allowed)


class PasswordAndHearingValidationTests(SimpleTestCase):
    def test_password_hash_command_recognizes_encoded_and_legacy_values(self):
        encoded = django_make_password("password-for-test")
        self.assertTrue(password_is_already_hashed(encoded))
        self.assertFalse(password_is_already_hashed("legacy-password-value"))
        self.assertTrue(password_is_already_hashed("!unusable"))

    def test_user_creation_hashes_password_without_exposing_it(self):
        role = Role(id=2, name="Court Clerk")
        serializer = UserManagementSerializer()
        with patch.object(User, "save") as save_user:
            user = serializer.create({
                "full_name": "Test Clerk",
                "email": "clerk@example.invalid",
                "phone": None,
                "role": role,
                "password": "Strong-Example-Password-2026",
            })

        self.assertTrue(check_password("Strong-Example-Password-2026", user.password_hash))
        self.assertNotEqual(user.password_hash, "Strong-Example-Password-2026")
        save_user.assert_called_once_with(force_insert=True)

    def test_hearing_serializer_rejects_existing_judge_or_room_conflict(self):
        judge = make_test_user("Judge")
        case = Case(id=10, assigned_judge_id=judge.pk)
        room = Courtroom(id=4, name="Test Room", status="Available")
        serializer = HearingSerializer(context={"request": Mock(method="POST")})
        query = Mock()
        query.exists.return_value = True

        with (
            patch.object(User.objects, "select_for_update", return_value=Mock(exists=Mock(return_value=True))),
            patch.object(Courtroom.objects, "select_for_update", return_value=Mock(exists=Mock(return_value=True))),
            patch.object(Hearing.objects, "filter", return_value=query),
        ):
            with self.assertRaises(Exception) as raised:
                serializer.validate({
                    "case": case,
                    "judge": judge,
                    "courtroom": room,
                    "hearing_date": date(2040, 1, 10),
                    "hearing_time": time(10, 30),
                    "status": "Scheduled",
                })

        self.assertIn("hearing_time", raised.exception.detail)


class CORSMiddlewareTests(SimpleTestCase):
    @override_settings(CORS_ALLOWED_ORIGINS=("http://localhost:5173",))
    def test_preflight_allows_an_approved_frontend(self):
        request = RequestFactory().options(
            "/api/cases/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        middleware = CORSMiddleware(lambda request: HttpResponse())

        response = middleware(request)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertIn(
            "authorization",
            response["Access-Control-Allow-Headers"].casefold(),
        )

    @override_settings(CORS_ALLOWED_ORIGINS=("http://localhost:5173",))
    def test_preflight_rejects_an_unapproved_frontend(self):
        request = RequestFactory().options(
            "/api/cases/",
            HTTP_ORIGIN="http://unknown.example",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        middleware = CORSMiddleware(lambda request: HttpResponse())

        response = middleware(request)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response)


def run_isolated_tests():
    """Run these mock-based tests without Django's database test setup."""
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1
