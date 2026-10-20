# Prompt: BarongClassifier Customer Auth + UI

Use this prompt when continuing work on `Customer/`.

## Structure

Build inside `Customer/` using:

- `app/routes/` — main, classifier, auth, history
- `app/templates/` + `app/templates/auth/` — Jinja pages matching `C:\Users\louis\Downloads\barong-classifier-ui.html`
- `app/static/css|js|images` — design tokens from the reference HTML
- Logo file: `app/static/images/Barongclassi_logo.jpeg`
- Postgres tables in schema `customer` (do not overwrite Supabase `public` auth tables)

## Required features

1. Register with email + password + confirm (≥12 chars).
2. Redirect to 6-box email verification; codes hashed, expire in **24 hours**.
3. Resend cooldown **60 seconds** from DB `resend_available_at`; timer survives refresh via `/auth/verification-status`.
4. Success modal → **Go to Login**.
5. Login; new/untrusted browser requires device verification email + HttpOnly `barong_device` cookie (hash stored).
6. Required nickname modal/page before Home / Classify / Textile Types / History.
7. Dashboard nav: Home, Classify Textile, Textile Types, History.
8. SMTP only from `.env`; never commit secrets.
9. Backend route guards for verification and nickname (not JS-only).
10. Preserve classification/history behavior; call classify server when available.

## Commands

```powershell
cd Customer
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:FLASK_APP = "app:create_app"
flask db upgrade
python -m pytest -q
flask run --host 127.0.0.1 --port 5000
```
