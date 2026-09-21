import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from pins.models import ContentCategory, Board, PinContent


def _placeholder_image(hex_color, label):
    """Tiny generated PNG so the dashboard has something to show without real assets."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 900), hex_color)
    draw = ImageDraw.Draw(img)
    draw.text((30, 420), label, fill="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name=f"{label.replace(' ', '_').lower()}.png")


class Command(BaseCommand):
    help = "Creates a superuser (admin/admin123), sample categories, boards, and pins for demoing the dashboard."

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@zeecomedia.com", "admin123")
            self.stdout.write(self.style.SUCCESS("Created superuser: admin / admin123"))

        categories = [
            ("AI News", "#6366F1", "sparkles"),
            ("Dev Tips", "#0EA5E9", "code-2"),
            ("Tech Reviews", "#F59E0B", "star"),
            ("Tutorials", "#10B981", "book-open"),
        ]
        cat_objs = {}
        for name, color, icon in categories:
            cat, _ = ContentCategory.objects.get_or_create(name=name, defaults={"color": color, "icon": icon})
            cat_objs[name] = cat

        boards = [
            ("AI & Automation", "AI News"),
            ("Python & Django", "Dev Tips"),
            ("Gadget Reviews", "Tech Reviews"),
            ("Coding Tutorials", "Tutorials"),
        ]
        board_objs = {}
        for name, cat_name in boards:
            board, _ = Board.objects.get_or_create(name=name, defaults={"category": cat_objs[cat_name]})
            board_objs[name] = board

        try:
            import PIL  # noqa: F401
        except ImportError:
            self.stdout.write(self.style.WARNING("Pillow not installed — skipping sample pins."))
            return

        sample_pins = [
            ("5 AI Tools Every Developer Needs in 2026", "AI & Automation", "AI News", PinContent.Status.POSTED, -2),
            ("Django ORM Tricks You're Not Using", "Python & Django", "Dev Tips", PinContent.Status.POSTED, -1),
            ("Is This the Best Laptop for Developers?", "Gadget Reviews", "Tech Reviews", PinContent.Status.SCHEDULED, 1),
            ("Build a REST API in 10 Minutes with FastAPI", "Coding Tutorials", "Tutorials", PinContent.Status.SCHEDULED, 2),
            ("How Large Language Models Actually Work", "AI & Automation", "AI News", PinContent.Status.DRAFT, 0),
        ]
        for title, board_name, cat_name, status, day_offset in sample_pins:
            if PinContent.objects.filter(title=title).exists():
                continue
            pin = PinContent(
                title=title,
                description=f"{title} — a Zeecomedia tech breakdown for developers and AI enthusiasts.",
                board=board_objs[board_name],
                category=cat_objs[cat_name],
                status=status,
                hashtags="#AI #WebDevelopment #TechTips #Zeecomedia",
                is_ai_generated=True,
            )
            when = timezone.now() + timedelta(days=day_offset)
            if status == PinContent.Status.POSTED:
                pin.posted_at = when
            elif status == PinContent.Status.SCHEDULED:
                pin.scheduled_for = when
            pin.image = _placeholder_image(cat_objs[cat_name].color, title[:20])
            pin.save()

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
