"""
Run this on a schedule (cron, Celery beat, systemd timer, etc.) — e.g. every 15 minutes —
to auto-post the next queued/scheduled pin according to AutomationSettings.

    python manage.py run_auto_post

It intentionally does NOT call the real Pinterest API yet — `publish_to_pinterest()`
below is the one place to plug that in once you have API credentials.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pins.models import AutomationSettings, PinContent, PostLog

WEEKDAY_FIELDS = [
    "post_monday",
    "post_tuesday",
    "post_wednesday",
    "post_thursday",
    "post_friday",
    "post_saturday",
    "post_sunday",
]


def publish_to_pinterest(pin, settings_obj):
    """
    Plug in the real Pinterest API v5 call here, e.g.:

        import requests
        resp = requests.post(
            "https://api.pinterest.com/v5/pins",
            headers={"Authorization": f"Bearer {settings_obj.pinterest_access_token}"},
            json={
                "board_id": pin.board.pinterest_board_id,
                "title": pin.title,
                "description": pin.description,
                "link": pin.destination_link,
                "media_source": {"source_type": "image_url", "url": pin.image.url},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    For now this is a no-op placeholder so the command can be wired into a
    scheduler safely before API credentials are in place.
    """
    raise NotImplementedError("Connect this to the Pinterest API before enabling automation.")


class Command(BaseCommand):
    help = "Posts the next due, queued/scheduled pin to Pinterest based on AutomationSettings."

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

        if not (settings_obj.daily_start_time <= now.time() <= settings_obj.daily_end_time):
            self.stdout.write("Outside today's posting window — skipping.")
            return

        candidates = PinContent.objects.filter(
            status__in=[PinContent.Status.SCHEDULED, PinContent.Status.QUEUED],
            scheduled_for__lte=timezone.now(),
        )
        if settings_obj.only_post_ai_flagged_content:
            candidates = candidates.filter(is_ai_generated=True)

        pin = candidates.order_by("scheduled_for").first()
        if not pin:
            self.stdout.write("No due pins to post.")
            return

        try:
            pinterest_id = publish_to_pinterest(pin, settings_obj)
        except Exception as exc:  # noqa: BLE001 — log any failure and move on
            pin.status = PinContent.Status.FAILED
            pin.failure_reason = str(exc)
            pin.save(update_fields=["status", "failure_reason"])
            PostLog.objects.create(pin=pin, result=PostLog.Result.FAILURE, message=str(exc))
            self.stderr.write(self.style.ERROR(f"Failed to post '{pin.title}': {exc}"))
            return

        pin.status = PinContent.Status.POSTED
        pin.posted_at = timezone.now()
        pin.pinterest_pin_id = pinterest_id
        pin.save(update_fields=["status", "posted_at", "pinterest_pin_id"])
        PostLog.objects.create(pin=pin, result=PostLog.Result.SUCCESS, message="Posted to Pinterest")
        self.stdout.write(self.style.SUCCESS(f"Posted '{pin.title}' to Pinterest."))
