from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import User


def user_has_role(user, expected_role):
    """Check a database user's current role name, ignoring letter case."""
    return (
        isinstance(user, User)
        and user.role.name.casefold() == expected_role.casefold()
    )


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, "Administrator")


class IsCourtClerk(BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, "Court Clerk")


class IsJudge(BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, "Judge")


class IsAuthenticatedUser(BasePermission):
    """The project's users table is separate from Django's auth_user table."""

    def has_permission(self, request, view):
        return isinstance(request.user, User)


class IsAdministratorOnly(BasePermission):
    def has_permission(self, request, view):
        return user_has_role(request.user, "Administrator")


class IsCourtStaffOrReadOnly(BasePermission):
    """Allow all signed-in roles to read; only clerks/admins can write."""

    def has_permission(self, request, view):
        if not isinstance(request.user, User):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == "DELETE":
            return user_has_role(request.user, "Administrator")
        return user_has_role(request.user, "Administrator") or user_has_role(
            request.user, "Court Clerk"
        )


class CaseAccessPermission(BasePermission):
    """Allow all court roles to read, clerks/admins to edit, admins to delete."""

    def has_permission(self, request, view):
        if not isinstance(request.user, User):
            return False

        if request.method in SAFE_METHODS:
            return user_has_role(request.user, "Administrator") or (
                user_has_role(request.user, "Court Clerk")
                or user_has_role(request.user, "Judge")
            )

        if request.method == "DELETE":
            return user_has_role(request.user, "Administrator")

        if request.method in ("POST", "PUT", "PATCH"):
            return user_has_role(request.user, "Administrator") or user_has_role(
                request.user, "Court Clerk"
            )

        return False
