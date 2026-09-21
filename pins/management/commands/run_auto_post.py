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

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from pins.models import AutomationSettings, DailyPostSlot, PinContent, PostLog

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


def publish_to_pinterest(pin, settings_obj):
    """Post `pin` to Pinterest via API v5. Returns the new Pinterest pin id."""
    import requests

    if not settings_obj.pinterest_access_token:
        raise RuntimeError("No Pinterest access token set in Automation Settings.")
    if not pin.board or not pin.board.pinterest_board_id:
        raise RuntimeError(f"'{pin.title}' has no linked Pinterest board ID — set one on its board.")

    image_url = _build_image_url(pin)

    payload = {
        "board_id": pin.board.pinterest_board_id,
        "title": pin.title,
        "description": pin.description,
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    if pin.destination_link:
        payload["link"] = pin.destination_link

    resp = requests.post(
        "https://api.pinterest.com/v5/pins",
        headers={
            "Authorization": f"Bearer {settings_obj.pinterest_access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Pinterest API error {resp.status_code}: {resp.text[:300]}")

    return resp.json()["id"]


class Command(BaseCommand):
    help = "Posts each window's due pin to Pinterest, once its randomly chosen daily time has passed."

    def handle(self, *args, **options):
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
                pin.status = PinContent.Status.FAILED
                pin.failure_reason = str(exc)
                pin.save(update_fields=["status", "failure_reason"])
                PostLog.objects.create(pin=pin, result=PostLog.Result.FAILURE, message=f"[{label}] {exc}")
                self.stderr.write(self.style.ERROR(f"Failed to post '{pin.title}' ({label}): {exc}"))
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