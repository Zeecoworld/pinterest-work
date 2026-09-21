"""
Generates pin images from a text prompt using a self-hosted, open-source
Stable Diffusion instance — specifically the AUTOMATIC1111 WebUI
(https://github.com/AUTOMATIC1111/stable-diffusion-webui), run with its
`--api` flag enabled. No third-party paid API, no data leaving your own
infrastructure.

Point SD_API_URL in `.env` at that instance (e.g. http://localhost:7860 if
it's running alongside this app, or the address of a GPU box on your
network) to enable real generation.

Without SD_API_URL set — or if the call fails for any reason (server not
running, model still loading, network hiccup, etc.) — this quietly falls
back to generating a branded placeholder image locally with Pillow, so
"Generate with AI" always works end-to-end even with no SD server up. The
caller is told which path was used (`used_real_api`) so the UI can be
honest about it.
"""

import base64
import io
import logging
import textwrap

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

PIN_WIDTH = 1000
PIN_HEIGHT = 1500

DEFAULT_NEGATIVE_PROMPT = (
    "text, watermark, logo, low quality, blurry, deformed, extra limbs, ugly"
)


def generate_pin_image(prompt: str, style: str = "") -> tuple[ContentFile, bool]:
    """
    Returns (ContentFile, used_real_api).

    `prompt` is the user's description of what the pin should show.
    `style` is an optional style suffix (e.g. from AutomationSettings'
    default_ai_image_style) appended to keep a consistent brand look.
    """
    full_prompt = f"{prompt.strip()}, {style.strip()}" if style.strip() else prompt.strip()

    if settings.SD_API_URL:
        try:
            return _generate_with_stable_diffusion(full_prompt), True
        except Exception:
            logger.exception("Self-hosted Stable Diffusion call failed — falling back to placeholder.")

    return _generate_placeholder(full_prompt), False


def _generate_with_stable_diffusion(prompt: str) -> ContentFile:
    """
    Calls a self-hosted AUTOMATIC1111 WebUI's txt2img API. Its `/sdapi/v1/txt2img`
    endpoint returns base64-encoded PNGs directly — no separate file host to fetch
    from, everything stays on your own server.

    Swap the checkpoint/sampler/steps below to taste, or point SD_API_URL at a
    ComfyUI instance instead and adjust this function to match its API shape
    (ComfyUI's is graph-based rather than a single JSON body, so the call itself
    would need to change, but the rest of this module — prompt building, the
    fallback, the return contract — stays the same).
    """
    import requests

    payload = {
        "prompt": prompt,
        "negative_prompt": settings.SD_NEGATIVE_PROMPT,
        "width": 832,
        "height": 1216,  # close to Pinterest's 2:3 pin ratio
        "steps": settings.SD_STEPS,
        "cfg_scale": settings.SD_CFG_SCALE,
        "sampler_name": "DPM++ 2M Karras",
    }
    resp = requests.post(
        f"{settings.SD_API_URL.rstrip('/')}/sdapi/v1/txt2img",
        json=payload,
        timeout=settings.SD_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()

    image_b64 = data["images"][0]
    # AUTOMATIC1111 sometimes prefixes a data URI header — strip it if present.
    if "," in image_b64[:50]:
        image_b64 = image_b64.split(",", 1)[1]
    image_bytes = base64.b64decode(image_b64)

    filename = f"ai_{abs(hash(prompt)) % 10**8}.png"
    return ContentFile(image_bytes, name=filename)


def _generate_placeholder(prompt: str) -> ContentFile:
    """Local, dependency-light fallback: a branded gradient card with the prompt on it."""
    from PIL import Image, ImageDraw, ImageFont

    # Deterministic-ish color from the prompt so repeated prompts look consistent.
    seed = sum(ord(c) for c in prompt) or 1
    hue_a = (seed * 37) % 360
    hue_b = (hue_a + 40) % 360
    top = _hsl_to_rgb(hue_a, 70, 45)
    bottom = _hsl_to_rgb(hue_b, 70, 30)

    img = Image.new("RGB", (PIN_WIDTH, PIN_HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(PIN_HEIGHT):
        t = y / PIN_HEIGHT
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (PIN_WIDTH, y)], fill=color)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    wrapped = textwrap.wrap(prompt, width=22)[:6]
    total_h = len(wrapped) * 58
    y = (PIN_HEIGHT - total_h) // 2
    for line in wrapped:
        w = draw.textlength(line, font=font)
        draw.text(((PIN_WIDTH - w) / 2, y), line, font=font, fill="white")
        y += 58

    label = "AI PREVIEW — set SD_API_URL for real images"
    lw = draw.textlength(label, font=small_font)
    draw.text(((PIN_WIDTH - lw) / 2, PIN_HEIGHT - 60), label, font=small_font, fill=(255, 255, 255, 180))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    filename = f"ai_preview_{abs(hash(prompt)) % 10**8}.png"
    return ContentFile(buf.getvalue(), name=filename)


def _hsl_to_rgb(h, s, l):
    import colorsys

    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return int(r * 255), int(g * 255), int(b * 255)
