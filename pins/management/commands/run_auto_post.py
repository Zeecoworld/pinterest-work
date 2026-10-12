"""
Run this on a schedule (Render cron, cron, Celery beat, systemd timer, etc.) —
frequently enough to land inside each posting window (e.g. every 15 minutes) —
to auto-post the day's queued pin for whichever window's random time has arrived.

    python manage.py run_auto_post

Each of the three windows (morning/afternoon/evening) gets ONE randomly chosen
target time per calendar day (see DailyPostSlot.get_or_create_for). This command
is safe to run often: it only actually posts once a window's target time has
passed AND that slot hasn't posted yet today.

Posting priority per slot:
1. The pin explicitly queued for that slot via the Daily Queue page (DailyPostSlot.pin).
2. Falls back to the oldest due SCHEDULED/QUEUED pin (the original behaviour),
   so manually scheduled content via the regular "New Pin" form still works.
"""

import base64
import logging

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from pins.models import AutomationSettings, DailyPostSlot, PinContent, PostLog
from pins.services import pinterest_oauth
from pins.services.notifications import notify_failure

logger = logging.getLogger(__name__)

# Give up on a pin for the day after this many failed attempts, so a permanent
# error (bad board ID, rejected image...) doesn't retry + email every 15 minutes.
MAX_ATTEMPTS_PER_PIN = 3

WEEKDAY_FIELDS = [
    "post_monday",
    "post_tuesday",
    "post_wednesday",
    "post_thursday",
    "post_friday",
    "post_saturday",
    "post_sunday",
]


def _build_image_url(pin):
    """
    Pinterest's API needs a publicly reachable image URL. Supabase Storage
    already returns a full https:// URL. Local disk storage returns a
    relative path, so it needs SITE_BASE_URL (set in .env) to be turned
    into an absolute URL Pinterest can actually fetch.
    """
    url = pin.image.url
    if url.startswith("http://") or url.startswith("https://"):
        return url

    site_base = getattr(django_settings, "SITE_BASE_URL", "")
    if not site_base:
        raise RuntimeError(
            "Pin image is on local disk and SITE_BASE_URL isn't set, so Pinterest "
            "can't fetch it. Set SITE_BASE_URL to your public domain in .env, or "
            "switch to Supabase Storage (USE_SUPABASE_STORAGE=true)."
        )
    return site_base.rstrip("/") + url


def _build_media_source(pin, settings_obj):
    """
    Returns the Pinterest API v5 `media_source` payload for `pin`.

    If overlay_title_on_image is on, the title gets composited onto an
    in-memory copy of the image (see title_overlay.py) and sent as base64 —
    which sidesteps needing a public URL for the edited version entirely.
    Otherwise, falls back to the original behaviour: a plain image_url
    pointing at the untouched stored image.
    """
    if settings_obj.overlay_title_on_image:
        import mimetypes

        from pins.services.title_overlay import overlay_title

        pin.image.open("rb")
        try:
            original_bytes = pin.image.read()
        finally:
            pin.image.close()
        content_type = mimetypes.guess_type(pin.image.name)[0] or "image/jpeg"

        edited_bytes, edited_content_type, used_gemini = overlay_title(original_bytes, content_type, pin.title)
        logger_suffix = "via Gemini" if used_gemini else "via local overlay"
        return {
            "source_type": "image_base64",
            "content_type": edited_content_type,
            "data": base64.b64encode(edited_bytes).decode("ascii"),
        }, logger_suffix

    return {"source_type": "image_url", "url": _build_image_url(pin)}, None


def publish_to_pinterest(pin, settings_obj):
    """Post `pin` to Pinterest via API v5. Returns the new Pinterest pin id."""
    import requests

    if not settings_obj.pinterest_access_token:
        raise RuntimeError("No Pinterest account connected — connect one in Automation Settings.")
    if not pin.board or not pin.board.pinterest_board_id:
        raise RuntimeError(f"'{pin.title}' has no linked Pinterest board ID — set one on its board.")

    # Refreshes the token first if it's expired/near-expiry, so a long-lived
    # cron job never gets stuck with a stale access token.
    access_token = pinterest_oauth.get_valid_access_token(settings_obj)

    media_source, overlay_note = _build_media_source(pin, settings_obj)

    description = pin.description
    if pin.hashtags:
        description = f"{description}\n\n{pin.hashtags}"

    payload = {
        "board_id": pin.board.pinterest_board_id,
        "title": pin.title[:100],
        "description": description[:800],
        "media_source": media_source,
    }
    if pin.alt_text:
        payload["alt_text"] = pin.alt_text[:500]
    if pin.destination_link:
        payload["link"] = pin.destination_link

    resp = requests.post(
        "https://api.pinterest.com/v5/pins",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Pinterest API error {resp.status_code}: {resp.text[:300]}")

    pin_id = resp.json()["id"]
    if overlay_note:
        logger.info(f"Posted '{pin.title}' with title overlay ({overlay_note}).")
    return pin_id


class Command(BaseCommand):
    help = "Posts each window's due pin to Pinterest, once its randomly chosen daily time has passed."

    def handle(self, *args, **options):
        # Anything that escapes _run() (DB down, bad config...) would otherwise
        # only show up in the cron logs. Email it, then re-raise so the cron
        # job still shows as failed.
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_auto_post crashed")
            notify_failure("Auto-post job crashed", f"{type(exc).__name__}: {exc}")
            raise

    def _run(self):
        settings_obj = AutomationSettings.load()

        if not settings_obj.is_enabled:
            self.stdout.write("Automation is disabled — nothing to do.")
            return

        now = timezone.localtime()
        today_field = WEEKDAY_FIELDS[now.weekday()]
        if not getattr(settings_obj, today_field):
            self.stdout.write(f"Today ({now.strftime('%A')}) is not an active posting day.")
            return

        slots = []
        for key, label, enabled, start, end in settings_obj.window_definitions():
            if not enabled:
                continue
            slot, _ = DailyPostSlot.get_or_create_for(now.date(), key, start, end)
            slots.append((label, slot))

        if not slots:
            self.stdout.write("No posting windows are enabled.")
            return

        due = [(label, slot) for label, slot in slots if not slot.completed and now.time() >= slot.planned_time]
        if not due:
            upcoming = ", ".join(
                f"{label} @ {slot.planned_time.strftime('%H:%M')}" for label, slot in slots if not slot.completed
            )
            self.stdout.write(f"No window's target time has arrived yet. Upcoming today: {upcoming or 'none left'}")
            return

        # Pins already earmarked for another (not-yet-posted) window's slot today
        # must not be grabbed by this window's generic fallback query below.
        reserved_pin_ids = {slot.pin_id for _, slot in slots if slot.pin_id and not slot.completed}

        for label, slot in due:
            pin = slot.pin
            if pin is None:
                candidates = PinContent.objects.filter(
                    status__in=[PinContent.Status.SCHEDULED, PinContent.Status.QUEUED],
                    scheduled_for__lte=timezone.now(),
                ).exclude(pk__in=reserved_pin_ids)
                if settings_obj.only_post_ai_flagged_content:
                    candidates = candidates.filter(is_ai_generated=True)
                pin = candidates.order_by("scheduled_for").first()

            if not pin:
                self.stdout.write(f"{label} slot's time has arrived, but nothing is queued to post — skipping.")
                continue

            try:
                pinterest_id = publish_to_pinterest(pin, settings_obj)
            except Exception as exc:  # noqa: BLE001 — log any failure and move on
                # failure_reason and PostLog.message are 255-char columns; an
                # untruncated Pinterest error body overflows them on Postgres and
                # crashes the job with a DataError instead of recording the failure.
                reason = str(exc)
                pin.status = PinContent.Status.FAILED
                pin.failure_reason = reason[:255]
                pin.save(update_fields=["status", "failure_reason"])
                PostLog.objects.create(
                    pin=pin, result=PostLog.Result.FAILURE, message=f"[{label}] {reason}"[:255]
                )
                self.stderr.write(self.style.ERROR(f"Failed to post '{pin.title}' ({label}): {exc}"))

                attempts = PostLog.objects.filter(
                    pin=pin, result=PostLog.Result.FAILURE, created_at__date=now.date()
                ).count()
                gave_up = attempts >= MAX_ATTEMPTS_PER_PIN
                if gave_up:
                    # Stop retrying this slot today; it won't be picked up again
                    # (FAILED pins are excluded from the fallback query).
                    slot.completed = True
                    slot.save(update_fields=["completed"])

                notify_failure(
                    f"Pin failed: {pin.title[:60]}",
                    (
                        f"Pin: {pin.title}\n"
                        f"Window: {label}\n"
                        f"Attempt: {attempts} of {MAX_ATTEMPTS_PER_PIN}"
                        f"{' — giving up for today' if gave_up else ' — will retry on the next run'}\n\n"
                        f"Error:\n{reason}\n\n"
                        "Common causes: Pinterest token/refresh failure (reconnect in Automation "
                        "Settings), missing board ID, or an image Pinterest couldn't fetch."
                    ),
                    settings_obj,
                )
                continue

            pin.status = PinContent.Status.POSTED
            pin.posted_at = timezone.now()
            pin.pinterest_pin_id = pinterest_id
            pin.save(update_fields=["status", "posted_at", "pinterest_pin_id"])
            PostLog.objects.create(
                pin=pin, result=PostLog.Result.SUCCESS, message=f"Posted to Pinterest ({label} slot)"
            )
            slot.completed = True
            slot.pin = pin
            slot.save(update_fields=["completed", "pin"])
            self.stdout.write(self.style.SUCCESS(f"Posted '{pin.title}' to Pinterest ({label})."))
