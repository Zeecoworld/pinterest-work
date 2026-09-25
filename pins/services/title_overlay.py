"""
Overlays each pin's title as legible text on its image, right before it's
posted to Pinterest — governed by AutomationSettings.overlay_title_on_image.

Same fallback shape as ai_image.py:

1. If GEMINI_API_KEY is set, ask Gemini (the "Nano Banana" image-editing
   model) to composite the title onto the image contextually — it can place
   text around the subject, add a shadow/gradient for contrast, etc., for a
   more designed look.
2. Always-available fallback: draw the title directly with Pillow. This runs
   whenever GEMINI_API_KEY isn't set, or if the Gemini call fails for any
   reason — including the model garbling the text, which is a known
   limitation of current text-in-image generation. Pillow guarantees the
   exact title renders correctly every time, just with a plainer look (a
   dark gradient band with white text along the bottom).

Either way, the ORIGINAL stored image is never modified — this only edits an
in-memory copy used for the Pinterest upload.
"""

import base64
import io
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def overlay_title(image_bytes: bytes, content_type: str, title: str) -> tuple[bytes, str, bool]:
    """
    Returns (edited_bytes, edited_content_type, used_gemini).
    Never raises — always returns something postable, so this feature can
    never be the reason a scheduled post fails.
    """
    if getattr(settings, "GEMINI_API_KEY", ""):
        try:
            edited_bytes, edited_content_type = _overlay_with_gemini(image_bytes, content_type, title)
            return edited_bytes, edited_content_type, True
        except Exception:
            logger.exception("Gemini title overlay failed — falling back to local text overlay.")

    return _overlay_with_pillow(image_bytes, title), "image/png", False


def _overlay_with_gemini(image_bytes: bytes, content_type: str, title: str) -> tuple[bytes, str]:
    import requests

    api_key = settings.GEMINI_API_KEY
    model = getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    url = GEMINI_ENDPOINT.format(model=model)

    prompt = (
        f'Add the text "{title}" as a bold, highly legible headline overlaid on this image. '
        "Position it where it doesn't cover the main subject — usually a band near the top or "
        "bottom third. Use a clean, modern sans-serif font with strong contrast against the "
        "background (add a subtle dark gradient or shadow behind the text if the background is "
        "busy). Keep everything else in the image — subject, composition, colors — exactly as "
        "it is. This image will be posted as a Pinterest pin, so it needs to read clearly as a "
        "thumbnail."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": content_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    for part in parts:
        inline = part.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), inline.get("mimeType", content_type)

    raise RuntimeError("Gemini response didn't include an image part.")


def _wrap_by_pixel_width(draw, text, font, max_width):
    """Word-wraps `text` so each line's rendered width stays under `max_width`."""
    words = text.split()
    if not words:
        return [text]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _overlay_with_pillow(image_bytes: bytes, title: str) -> bytes:
    """Deterministic fallback: draws `title` directly onto the image with Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    font_size = max(28, width // 16)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    max_line_width = width * 0.9
    lines = _wrap_by_pixel_width(draw, title, font, max_line_width)[:4]
    line_height = int(font_size * 1.25)
    band_height = line_height * len(lines) + 40

    # Dark gradient band along the bottom for contrast, regardless of what's
    # underneath — drawn on a transparent layer, then composited.
    band = Image.new("RGBA", (width, band_height), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band)
    for y in range(band_height):
        alpha = int(170 * (y / band_height))
        band_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    img.paste(band, (0, height - band_height), band)

    y = height - band_height + 20
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((width - w) / 2, y), line, font=font, fill="white")
        y += line_height

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
