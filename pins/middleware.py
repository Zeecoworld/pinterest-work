"""
Optional HTTP Basic Auth in front of the whole dashboard.

Turned on by setting DASHBOARD_USER and DASHBOARD_PASSWORD (e.g. in the Render
dashboard). If either is unset, this middleware does nothing, so local
development and existing deployments keep working unchanged.

Left open on purpose:
  /privacy/  - Pinterest's app review may need to load the privacy policy.
  /media/    - when images are on local disk, Pinterest fetches them from here.
  /static/   - CSS/JS.
Everything else, including /admin/ and the Pinterest OAuth callback, needs the
password (your browser sends it automatically once you've signed in).
"""

import base64
import hmac

from django.conf import settings
from django.http import HttpResponse

OPEN_PREFIXES = ("/privacy/", "/media/", "/static/")


class DashboardBasicAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(settings, "DASHBOARD_USER", "")
        password = getattr(settings, "DASHBOARD_PASSWORD", "")
        if not (user and password) or request.path.startswith(OPEN_PREFIXES):
            return self.get_response(request)

        if self._credentials_ok(request, user, password):
            return self.get_response(request)

        response = HttpResponse("Authentication required.", status=401)
        response["WWW-Authenticate"] = 'Basic realm="Zeecomedia Pinterest Dashboard", charset="UTF-8"'
        return response

    @staticmethod
    def _credentials_ok(request, user, password):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return False
        try:
            given_user, _, given_password = base64.b64decode(encoded).decode("utf-8").partition(":")
        except Exception:  # noqa: BLE001 — malformed header
            return False
        # compare_digest avoids leaking info via response timing.
        user_ok = hmac.compare_digest(given_user.encode(), user.encode())
        password_ok = hmac.compare_digest(given_password.encode(), password.encode())
        return user_ok and password_ok
