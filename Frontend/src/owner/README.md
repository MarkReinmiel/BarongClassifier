# BarongClassifier Owner Portal

Flask Owner Portal for authorized `owner` accounts: secure login, Cloudflare Turnstile, SMTP password recovery with 6-digit codes, and a protected dashboard.

Uses the existing `customer.users` table and `customer.email_verifications` (purpose `password_reset`). Does not replace Backend/Frontend or the classification model.

## Prerequisites

- Python 3.11+
- Postgres (same Supabase/project DB as Customer)
- SMTP credentials (Gmail App Password recommended)
- Cloudflare Turnstile site/secret keys when `TURNSTILE_ENABLED=true`

## Setup (PowerShell)

```powershell
cd "C:\Users\Nitro\Documents\BarongClassifier\Frontend\src\owner"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with database, SMTP, `SECRET_KEY`, and Turnstile values. Do not commit `.env`.

Optional dataset link (already created if you ran setup):

```powershell
# junctions under Frontend\src\owner\datasets\{cocoon,jusi,pina} → repo dataset\
```

## Run

```powershell
cd "C:\Users\Nitro\Documents\BarongClassifier\Frontend\src\owner"
.\.venv\Scripts\Activate.ps1
$env:FLASK_APP = "app:create_app"
$env:PYTHONPATH = "."
python -m pip install -r requirements-ml.txt
flask run --host=127.0.0.1 --port=5001
```

- Login: http://127.0.0.1:5001/login  
- Dashboard: http://127.0.0.1:5001/dashboard  
- Classify: http://127.0.0.1:5001/classify  

Owner Flask app lives at `Frontend/src/owner`. Shared static reference UI remains under `Frontend/src/pages`.
## SMTP

Uses `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM_ADDRESS`, TLS on 587 (or SSL on 465 via `MAIL_USE_SSL=true`). Failed sends raise an error — the UI will not claim success.

## Password recovery

1. `/forgot-password` — requires an existing Owner row with `password_hash` (error if missing).
2. Turnstile checkbox before send.
3. 6-digit code emailed; 60s server-side resend cooldown.
4. `/verify-reset-code` then `/reset-password`.

## Turnstile

Set `TURNSTILE_ENABLED=true` plus site/secret keys. Login and forgot-password forms embed the widget; the server verifies `cf-turnstile-response`.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Production notes

- Set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Use a long random `SECRET_KEY`.
- Do not use the Flask development server in production.
