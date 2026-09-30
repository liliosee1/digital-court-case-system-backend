from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


class CORSMiddleware:
    """Allow browser API calls from explicitly configured frontend origins."""

    allowed_methods = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
    allowed_headers = {"authorization", "content-type", "accept", "x-requested-with"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        if (
            request.method == "OPTIONS"
            and request.headers.get("Access-Control-Request-Method")
        ):
            response = self._preflight_response(request, origin)
        else:
            response = self.get_response(request)

        return self._add_cors_headers(response, origin)

    def _preflight_response(self, request, origin):
        requested_method = request.headers.get("Access-Control-Request-Method", "").upper()
        requested_headers = {
            item.strip().lower()
            for item in request.headers.get("Access-Control-Request-Headers", "").split(",")
            if item.strip()
        }
        if (
            origin not in settings.CORS_ALLOWED_ORIGINS
            or requested_method not in self.allowed_methods
            or not requested_headers.issubset(self.allowed_headers)
        ):
            return HttpResponse(status=403)

        return HttpResponse(status=204)

    def _add_cors_headers(self, response, origin):
        if origin not in settings.CORS_ALLOWED_ORIGINS:
            return response

        response["Access-Control-Allow-Origin"] = origin
        patch_vary_headers(response, ("Origin",))

        if response.status_code == 204:
            response["Access-Control-Allow-Methods"] = ", ".join(
                sorted(self.allowed_methods)
            )
            response["Access-Control-Allow-Headers"] = ", ".join(
                sorted(self.allowed_headers)
            )
            response["Access-Control-Max-Age"] = "86400"

        return response
