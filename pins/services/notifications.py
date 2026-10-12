"""
Failure alert emails, sent through whatever EMAIL_* backend is configured in
settings.py (Brevo SMTP relay in production).

Never raises: an alert that can't be delivered must not break the posting
job itself — it's logged instead.
"""

import logging

from django.conf import settings as django_settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _recipient(settings_obj):
    if settings_obj is not None:
        if not settings_obj.notify_on_failure:
            return None
        if settings_obj.notification_email:
            return settings_obj.notification_email
    return getattr(django_settings, "ALERT_EMAIL_FALLBACK", "") or None


def notify_failure(subject, body, settings_obj=None):
    """Email a failure alert. Returns True if it was handed to the mail server."""
    to = _recipient(settings_obj)
    if not to:
        logger.warning("Failure alert not sent (notifications off or no recipient): %s", subject)
        return False
    try:
        send_mail(
            subject=f"[Zeecomedia Pinterest] {subject}",
            message=body,
            from_email=None,  # DEFAULT_FROM_EMAIL
            recipient_list=[to],
            fail_silently=False,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Couldn't send failure alert email: %s", subject)
        return False
