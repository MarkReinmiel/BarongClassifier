# BarongClassifier Customer App

Flask customer portal for registration, email verification, trusted-device checks, nickname setup, and textile classification.

## Design

UI follows `barong-classifier-ui.html` (DM Sans / Playfair Display, warm paper background, purple accent). Brand logo: `app/static/images/Barongclassi_logo.jpeg`.

## Setup

```powershell
cd Frontend\src\customer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
copy .env.example .env
```

Fill SMTP and database values in `.env`. Use a Gmail App Password for `MAIL_PASSWORD`. Set:

- Session pooler host/port for Supabase Postgres (`DB_HOST` / `DB_PORT=5432`) or `DATABASE_URL`
- `EMAIL_VERIFICATION_EXPIRE_MINUTES=1440` (24 hours)
- `EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=60`

Apply schema migrations (do not use `create_all` in production):

```powershell
$env:FLASK_APP = "app:create_app"
$env:PYTHONPATH = "."
flask db current
flask db upgrade
```

Database details: `docs/DATABASE.md`.

Run:

```powershell
flask run --host 127.0.0.1 --port 5000
```

Open http://127.0.0.1:5000/auth/register

Health check: http://127.0.0.1:5000/health

## Trusted devices

A successful new-device verification stores only a hash of an opaque token. The browser keeps the token in an HttpOnly cookie named `barong_device`. This identifies a trusted browser profile, not a guaranteed unique physical device. Private browsing or clearing cookies looks like a new device.

## Tests

```powershell
python -m pytest -q
```

Email sending is mocked in automated tests.

## Local CNN (train + test)

The trained MobileNetV2 model and dataset live under `Frontend/src/customer/models/` and `Frontend/src/customer/datasets/`.

```powershell
cd Frontend\src\customer
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ml.txt
python scripts/setup_ml_assets.py
# optional retrain (~20 min on CPU):
python scripts/train_cnn.py
flask run --host 127.0.0.1 --port 5000
```

Classification uses `models/barong_model.keras` when `CLASSIFY_SERVER_URL` is empty. Set `CLASSIFY_SERVER_URL=http://127.0.0.1:5501/predict` only if you run the Backend classify server instead.

## Production notes

- Set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Keep `SECRET_KEY` long and random.
- Back up Postgres before migrations.
- Prefer the local model (`MODEL_PATH`) for Customer; optional remote via `CLASSIFY_SERVER_URL`.
