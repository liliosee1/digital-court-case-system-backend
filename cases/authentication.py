from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import User


TOKEN_SALT = "cases.api.access-token"
TOKEN_MAX_AGE_SECONDS = 8 * 60 * 60  # Eight hours


class BearerTokenAuthentication(BaseAuthentication):
    """Authenticate API requests with a short-lived signed Bearer token."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None

        if parts[0].lower() != b"bearer":
            return None

        if len(parts) != 2:
            raise AuthenticationFailed("Invalid authorization header.")

        try:
            token_data = signing.loads(
                parts[1].decode("utf-8"),
                key=settings.SECRET_KEY,
                salt=TOKEN_SALT,
                max_age=TOKEN_MAX_AGE_SECONDS,
            )
            user = User.objects.select_related("role").get(pk=token_data["user_id"])
        except (UnicodeDecodeError, signing.BadSignature, KeyError, TypeError, ValueError):
            raise AuthenticationFailed("Invalid or expired token.")
        except User.DoesNotExist:
            raise AuthenticationFailed("Invalid or expired token.")

        return (user, token_data)

    def authenticate_header(self, request):
        return "Bearer"
