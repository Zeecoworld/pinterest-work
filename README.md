# Zeecomedia Pinterest Content Manager

A Django dashboard for planning, scheduling, and (eventually) auto-posting
Pinterest content for the Zeecomedia brand — built for near-daily tech/AI pins.
Runs on Supabase Postgres, and can generate pin images with AI.

## Features

- **Dashboard** — pin counts, 7-day posting activity chart, category
  breakdown, upcoming scheduled pins, automation status
- **Content manager** — grid view with filters, create/edit form with image
  upload OR AI image generation + live preview, detail page, delete
  confirmation
- **AI-generated pin images** — describe what you want on the "New Pin" page
  and generate it directly, via your own self-hosted, open-source Stable
  Diffusion server. Works out of the box even with no server running yet
  (falls back to a local placeholder preview so you can build/test the
  flow before your GPU box is up)
- **Calendar** — month view of scheduled/posted pins
- **Boards & Categories** — organize pins by Pinterest board and content theme
- **Automation settings** — on/off switch, Pinterest API token fields,
  posting frequency & time window, active weekdays, content rules
  (auto-hashtags, AI-flagged-only posting, default AI image style), failure
  email notifications
- **`run_auto_post` management command** — the hook point for real automation
  (cron / Celery beat / systemd timer); the Pinterest API call itself is left
  as one clearly-marked function (`publish_to_pinterest`) for you to fill in
  with your API credentials
- **No login wall** — the dashboard is open by default (see "Access control"
  below if you want to put it behind auth again, e.g. for a public server)

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env          # then fill in your Supabase + API details
python manage.py migrate
python manage.py seed_demo_data   # creates admin/admin123 (for /admin/ only) + sample content
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — no login required. Django's own `/admin/`
is still there and still requires the `admin` / `admin123` login created by
`seed_demo_data` (change that password — see below).

## Connecting Supabase (database)

1. In your Supabase project: **Project Settings → Database → Connection
   string (URI)**. Copy the "Transaction pooler" URL (port 6543) — that's
   the one most hosting platforms need.
2. Paste it into `.env` as `DATABASE_URL`.
3. Run `python manage.py migrate` again against it, then `seed_demo_data`
   if you want sample content.

Leave `DATABASE_URL` blank and the app falls back to local SQLite — handy
for quick local testing without touching Supabase at all.

### Optional: Supabase Storage for pin images

By default, uploaded/generated images are saved to local disk
(`MEDIA_ROOT`), which is fine for a single always-on server. If you deploy
somewhere with an ephemeral filesystem (serverless, some PaaS setups),
switch to Supabase Storage instead:

1. In Supabase: **Storage → New bucket** (e.g. `pin-images`). Make it public
   if you want plain image URLs; otherwise you'll need to adapt
   `pins/storage.py` to issue signed URLs.
2. In **Project Settings → API**, copy the `service_role` key (server-side
   only — never expose it to a browser).
3. In `.env`, set `USE_SUPABASE_STORAGE=true`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET`.

## Connecting AI image generation (self-hosted, open source)

Image generation runs against your own Stable Diffusion server — no paid
third-party API, nothing leaves your infrastructure.

1. Stand up [AUTOMATIC1111's Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
   somewhere with a GPU (your own machine, a rented GPU box, etc.), started
   with its API enabled:
   ```bash
   ./webui.sh --api --listen        # Linux/macOS
   webui-user.bat with --api added   # Windows
   ```
   This exposes `POST /sdapi/v1/txt2img` on port 7860 by default. Any SD 1.5
   or SDXL checkpoint you have installed there works — pick whichever gives
   results you like for tech/illustration-style pins.
2. In `.env`, set `SD_API_URL` to that server's address (e.g.
   `http://localhost:7860` if it's on the same machine, or
   `http://192.168.x.x:7860` / a tunnelled URL if it's on another box).
   `SD_STEPS`, `SD_CFG_SCALE`, and `SD_NEGATIVE_PROMPT` are tunable too.
3. On the "New Pin" page, switch to the **Generate** tab, describe the
   image, and click **Generate image**. It fills the image field directly —
   no separate upload step needed.
4. Set a **Default AI image style** in Automation Settings (e.g. "flat
   vector illustration, vibrant colors, tech blog aesthetic") to keep a
   consistent look across pins — it's appended to every prompt automatically.

Without `SD_API_URL` set (or if the server is unreachable), generation still
works end-to-end but returns a labeled placeholder image instead of a real
one, so you can build and test the flow before your GPU box is running.

Prefer ComfyUI instead of AUTOMATIC1111? Its API is graph-based rather than
a single JSON body, so swap `_generate_with_stable_diffusion()` in
`pins/services/ai_image.py` for a call to your ComfyUI workflow — everything
else (prompt building, the fallback, the return contract) stays the same.

## Connecting Pinterest for real

1. Create an app at <https://developers.pinterest.com/> and generate an
   access token with the `boards:read`, `pins:read`, `pins:write` scopes.
2. Go to **Automation Settings** in the dashboard and paste the token + app
   ID, pick a default board, set your posting window/frequency/days.
3. Open `pins/management/commands/run_auto_post.py` and implement
   `publish_to_pinterest()` with the real API call (a commented example
   using `requests` is already in the docstring).
4. Schedule the command to run regularly, e.g. every 15 minutes:
   ```bash
   */15 * * * * cd /path/to/project && venv/bin/python manage.py run_auto_post
   ```
   Or wire it into Celery beat if you're already running Celery elsewhere.

The command respects everything set in Automation Settings: it only posts
on active weekdays, inside the configured time window, and (optionally)
only content flagged as AI-generated.

## Access control

The dashboard itself has no login requirement — every `pins` view is public.
`/admin/` (Django's built-in admin) still requires a login, which is useful
for quick data fixes without exposing it as part of the main app. If you
later deploy this somewhere public and want the dashboard itself gated too,
re-add `from django.contrib.auth.decorators import login_required` and the
`@login_required` decorator to the view functions in `pins/views.py` (it was
deliberately removed, not deleted from Django — `LOGIN_URL` and the login
template are both still in place and wired up), or simplest: put the whole
app behind your reverse proxy's own auth (e.g. basic auth in Nginx) instead.

## Production notes

- Set `DJANGO_DEBUG=false`, a real `DJANGO_SECRET_KEY`, and proper
  `DJANGO_ALLOWED_HOSTS` in `.env` — never commit `.env` itself.
- `DATABASE_URL` pointed at Supabase already gives you a production-ready
  Postgres; no further DB changes needed.
- Consider putting the app behind auth at the proxy level if you deploy it
  somewhere public, since the dashboard has no login of its own (see above).
- Change the default `/admin/` password immediately:
  `python manage.py changepassword admin`

## Project structure

```
config/          Django project settings & root URLs
pins/            The app: models, views, forms, admin, templates
  services/               ai_image.py — self-hosted Stable Diffusion call + local fallback
  storage.py               Optional Supabase Storage backend
  templates/pins/          Dashboard, content, calendar, boards, categories, settings
  templates/registration/  Login page (kept, but not required by any view)
  management/commands/    run_auto_post.py, seed_demo_data.py
media/           Uploaded/generated pin images (created at runtime, unless using Supabase Storage)
.env.example     Copy to .env and fill in your values
```
