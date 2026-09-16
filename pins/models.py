import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone


class ContentCategory(models.Model):
    """Buckets like 'AI News', 'Dev Tips', 'Tech Reviews' used to tag & theme pins."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    color = models.CharField(
        max_length=7,
        default="#6366F1",
        help_text="Hex color used as the category badge/accent (e.g. #6366F1).",
    )
    icon = models.CharField(
        max_length=40,
        default="sparkles",
        help_text="Lucide icon name shown next to the category.",
    )

    class Meta:
        verbose_name_plural = "Content categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Board(models.Model):
    """A Pinterest board that content can be published to."""

    name = models.CharField(max_length=120)
    pinterest_board_id = models.CharField(
        max_length=120,
        blank=True,
        help_text="Board ID from Pinterest (filled once connected via the API).",
    )
    category = models.ForeignKey(
        ContentCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="boards"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PinContent(models.Model):
    """A single piece of content — draft, scheduled, or already posted to Pinterest."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        QUEUED = "queued", "Queued for posting"
        POSTED = "posted", "Posted"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100)
    description = models.TextField(
        max_length=500, help_text="Pinterest pin description (keep it keyword-rich)."
    )
    destination_link = models.URLField(
        blank=True, help_text="Where the pin should send traffic (blog post, landing page, etc.)."
    )
    image = models.ImageField(upload_to="pins/%Y/%m/")
    alt_text = models.CharField(max_length=500, blank=True)
    hashtags = models.CharField(
        max_length=300, blank=True, help_text="Space separated, e.g. #AI #Python #WebDev"
    )

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="pins")
    category = models.ForeignKey(
        ContentCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="pins"
    )

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    scheduled_for = models.DateTimeField(
        null=True, blank=True, help_text="When this pin should go out."
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    pinterest_pin_id = models.CharField(max_length=120, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    is_ai_generated = models.BooleanField(
        default=False, help_text="Flag content whose copy/image was produced by an AI tool."
    )
    ai_prompt = models.CharField(
        max_length=500,
        blank=True,
        help_text="The prompt used to generate this pin's image, if it was AI-generated.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("pins:content_detail", args=[self.id])

    @property
    def is_overdue(self):
        return (
            self.status == self.Status.SCHEDULED
            and self.scheduled_for
            and self.scheduled_for < timezone.now()
        )


class AutomationSettings(models.Model):
    """
    Singleton-style settings row controlling auto-posting behaviour.
    Only one row is expected to exist (enforced in the admin/view layer).
    """

    class Frequency(models.TextChoices):
        ONCE_DAILY = "1_day", "Once a day"
        TWICE_DAILY = "2_day", "Twice a day"
        THREE_DAILY = "3_day", "Three times a day"
        CUSTOM = "custom", "Custom interval"

    is_enabled = models.BooleanField(
        default=False, help_text="Master switch — turn automated posting on or off."
    )

    pinterest_access_token = models.CharField(
        max_length=500,
        blank=True,
        help_text="Pinterest API access token (stored server-side, never shown in the UI).",
    )
    pinterest_app_id = models.CharField(max_length=200, blank=True)

    default_board = models.ForeignKey(
        Board, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    posting_frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.ONCE_DAILY
    )
    custom_interval_hours = models.PositiveSmallIntegerField(
        default=6, help_text="Only used when frequency is 'Custom interval'."
    )

    daily_start_time = models.TimeField(
        default="09:00", help_text="Earliest time of day a post can go out."
    )
    daily_end_time = models.TimeField(
        default="20:00", help_text="Latest time of day a post can go out."
    )

    post_monday = models.BooleanField(default=True)
    post_tuesday = models.BooleanField(default=True)
    post_wednesday = models.BooleanField(default=True)
    post_thursday = models.BooleanField(default=True)
    post_friday = models.BooleanField(default=True)
    post_saturday = models.BooleanField(default=True)
    post_sunday = models.BooleanField(default=True)

    auto_generate_hashtags = models.BooleanField(default=True)
    only_post_ai_flagged_content = models.BooleanField(
        default=False,
        help_text="If on, automation only picks up content marked 'AI generated'.",
    )
    default_ai_image_style = models.CharField(
        max_length=200,
        blank=True,
        default="flat vector illustration, vibrant colors, tech blog aesthetic",
        help_text="Appended to every AI image prompt to keep a consistent brand look.",
    )
    notify_on_failure = models.BooleanField(default=True)
    notification_email = models.EmailField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Automation settings"
        verbose_name_plural = "Automation settings"

    def __str__(self):
        return "Automation settings"

    def active_weekdays(self):
        days = []
        mapping = [
            (0, self.post_monday, "Mon"),
            (1, self.post_tuesday, "Tue"),
            (2, self.post_wednesday, "Wed"),
            (3, self.post_thursday, "Thu"),
            (4, self.post_friday, "Fri"),
            (5, self.post_saturday, "Sat"),
            (6, self.post_sunday, "Sun"),
        ]
        for idx, enabled, label in mapping:
            if enabled:
                days.append(label)
        return days

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PostLog(models.Model):
    """History of automated (or manual) posting attempts, for the activity feed."""

    class Result(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    pin = models.ForeignKey(
        PinContent, on_delete=models.CASCADE, related_name="logs", null=True, blank=True
    )
    result = models.CharField(max_length=10, choices=Result.choices)
    message = models.CharField(max_length=255, blank=True)
    triggered_by = models.CharField(
        max_length=20,
        default="automation",
        help_text="'automation' or 'manual'",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_result_display()} — {self.pin_id}"
