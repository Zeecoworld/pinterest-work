"""
Pinterest OAuth 2.0 (Authorization Code grant), API v5.

This is the full "Continue with Pinterest" flow: redirect the user to
Pinterest to approve access, receive an authorization code back, exchange it
for an access + refresh token, and keep that token fresh afterwards. See
https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/

Three moving pieces:
  - build_authorization_url()   -> step 1, where we send the user
  - exchange_code_for_token()   -> step 3, after Pinterest redirects back with ?code=
  - get_valid_access_token()    -> called before every API request; refreshes
                                    the token first if it's expired or close to it

pinterest_access_token on AutomationSettings is the single source of truth
for "are we connected" — the manual-paste field in Automation Settings and
the token this flow stores are the same field, so either path works.
"""

import base64
import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings as django_settings
from django.utils import timezone

logger = logging.getLogger(__name__)

AUTHORIZATION_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
API_BASE = "https://api.pinterest.com/v5"

# Minimum scopes to read the connected account, read/write boards, and
# create pins. Trim or extend as your app's Pinterest review scope grant
# changes — must be a subset of what's approved for your app in
# developers.pinterest.com/apps.
DEFAULT_SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"

# Refresh this many seconds before actual expiry, so a slow API call never
# gets caught using a token that just expired mid-request.
REFRESH_SKEW_SECONDS = 300


class PinterestOAuthError(RuntimeError):
    """Raised for any failure talking to Pinterest's OAuth endpoints."""


def _client_credentials():
    client_id = getattr(django_settings, "PINTEREST_CLIENT_ID", "")
    client_secret = getattr(django_settings, "PINTEREST_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise PinterestOAuthError(
            "PINTEREST_CLIENT_ID / PINTEREST_CLIENT_SECRET aren't set. Add them to .env "
            "(from your app's page at developers.pinterest.com/apps) before connecting."
        )
    return client_id, client_secret


def _basic_auth_header():
    client_id, client_secret = _client_credentials()
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def get_redirect_uri(request):
    """
    Absolute callback URL Pinterest sends the user back to. Must match,
    character for character, a redirect URI registered on the app at
    developers.pinterest.com/apps. Override with PINTEREST_REDIRECT_URI in
    .env if this app sits behind a proxy/domain that request.build_absolute_uri
    can't see correctly.
    """
    configured = getattr(django_settings, "PINTEREST_REDIRECT_URI", "")
    if configured:
        return configured
    from django.urls import reverse

    return request.build_absolute_uri(reverse("pins:pinterest_oauth_callback"))


def build_authorization_url(request, state):
    client_id, _ = _client_credentials()
    scopes = getattr(django_settings, "PINTEREST_SCOPES", DEFAULT_SCOPES)
    params = {
        "client_id": client_id,
        "redirect_uri": get_redirect_uri(request),
        "response_type": "code",
        "scope": scopes,
        "state": state,
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def exchange_code_for_token(request, code):
    """Step 3 of the flow: trade the authorization code for tokens."""
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_redirect_uri(request),
            "continuous_refresh": "true",
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise PinterestOAuthError(f"Pinterest token exchange failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def refresh_token(refresh_token_value):
    """Exchange a refresh token for a new access token (and rolled-forward refresh token)."""
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_value,
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise PinterestOAuthError(f"Pinterest token refresh failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def fetch_account_info(access_token):
    resp = requests.get(
        f"{API_BASE}/user_account",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise PinterestOAuthError(f"Couldn't fetch Pinterest account info ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def fetch_boards(access_token):
    """Returns every board (paginated) on the connected account: [{id, name, ...}, ...]."""
    boards = []
    url = f"{API_BASE}/boards"
    params = {"page_size": 100}
    while url:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise PinterestOAuthError(f"Couldn't fetch Pinterest boards ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        boards.extend(data.get("items", []))
        bookmark = data.get("bookmark")
        if not bookmark:
            break
        params = {"page_size": 100, "bookmark": bookmark}
    return boards


def store_token_response(settings_obj, token_data):
    """Persist an OAuth token response (from either exchange or refresh) onto AutomationSettings."""
    settings_obj.pinterest_access_token = token_data["access_token"]
    if token_data.get("refresh_token"):
        settings_obj.pinterest_refresh_token = token_data["refresh_token"]
    expires_in = token_data.get("expires_in")
    if expires_in:
        settings_obj.pinterest_token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
    settings_obj.save(
        update_fields=["pinterest_access_token", "pinterest_refresh_token", "pinterest_token_expires_at"]
    )


def get_valid_access_token(settings_obj):
    """
    Returns a Pinterest access token that's good to use right now, refreshing
    it first via the stored refresh token if it's expired (or about to be).
    Call this instead of reading settings_obj.pinterest_access_token directly
    anywhere that's about to make a live API call.
    """
    if not settings_obj.pinterest_access_token:
        raise PinterestOAuthError("No Pinterest account connected yet — connect it in Automation Settings.")

    expires_at = settings_obj.pinterest_token_expires_at
    needs_refresh = expires_at is not None and timezone.now() >= (
        expires_at - timedelta(seconds=REFRESH_SKEW_SECONDS)
    )
    if needs_refresh and settings_obj.pinterest_refresh_token:
        token_data = refresh_token(settings_obj.pinterest_refresh_token)
        store_token_response(settings_obj, token_data)
        logger.info("Refreshed Pinterest access token for automation settings.")

    return settings_obj.pinterest_access_token
