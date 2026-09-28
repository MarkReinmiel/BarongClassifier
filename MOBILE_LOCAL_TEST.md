# Testing BarongClassifier from your phone (same Wi-Fi, no deployment)

The website and the CNN both keep running on the laptop. The phone only opens the
site in its browser over your home Wi-Fi.

```
Phone browser
   │  http://<LAPTOP_IP>:5500/Frontend/src/pages/...     (website, python -m http.server)
   │  http://<LAPTOP_IP>:5501/predict                    (CNN, classify_server.py)
   ▼
Laptop ── Backend/machine learning/artifacts/barong_mobilenetv2.keras
```

| Part | Command / file | Port |
| --- | --- | --- |
| Website (HTML/CSS/JS, Supabase login) | `python -m http.server 5500` from the project root | 5500 |
| CNN classifier | `python "Backend/machine learning/classify_server.py" --host 0.0.0.0` | 5501 |

The site works out the classifier address from the address in the browser bar
(`Frontend/src/js/apiConfig.js`), so nothing needs editing when your laptop's IP changes.

---

## 1. Open the project

Open the `BarongClassifier` folder in VS Code / Cursor and open **two** terminals
(PowerShell). Both terminals must be in the project root:

```powershell
cd C:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier
```

## 2. Python environment

The project has no virtual environment; it uses the installed Python 3.12, which
already has TensorFlow. If you are on a new machine, install the requirements once:

```powershell
pip install -r "Backend/machine learning/requirements.txt"
```

(If you later create a venv, activate it first with `.\.venv\Scripts\Activate.ps1`.)

## 3. Terminal 1 — start the CNN classifier on the local network

```powershell
python "Backend/machine learning/classify_server.py" --host 0.0.0.0
```

Wait until it prints something like:

```
Classifier ready at http://127.0.0.1:5501/predict
Phone check (same Wi-Fi): http://192.168.1.55:5501/health
Leave this running while you use the result page.
```

The `Phone check` line shows your laptop's current Wi-Fi IP. Leave this terminal open;
each classification is printed here, including the phone's IP.

Without `--host 0.0.0.0` the classifier only accepts connections from the laptop itself
(the previous behaviour).

## 4. Terminal 2 — start the website

```powershell
python -m http.server 5500
```

This already listens on every network interface, so the phone can reach it.

## 5. Find the laptop's IPv4 address

Either read it from the `Phone check` line above, or run:

```powershell
ipconfig
```

Look under **Wireless LAN adapter Wi-Fi** for **IPv4 Address**, e.g. `192.168.1.55`.
The address can change after reconnecting to Wi-Fi, so check it each session.

## 6. Connect the phone

Connect the phone to the **same Wi-Fi network** as the laptop (not mobile data, not a
guest network).

1. On the phone, open `http://<LAPTOP_IP>:5501/health`
   You should see `{"status": "ok", ...}`. If not, see Troubleshooting.
2. Open the site: `http://<LAPTOP_IP>:5500/Frontend/src/pages/index.html`
   Type `http://` explicitly and include `/Frontend/src/pages/`.

## 7. Log in

Tap **Get Started** and log in with your existing Supabase account. Login works from
any address because Supabase is reached over the internet from the phone. The phone
has its own session, so you log in once per device.

## 8. Test gallery upload + CNN prediction

1. Go to **Classify**. Under the Classify button it should say
   `Classification server connected (<LAPTOP_IP>:5501)`.
2. Tap **Upload from Gallery** and choose a JPG or PNG photo.
3. Tap **Classify Textile**.
4. The Result page shows the photo, **Predicted Textile Type**, **Model Confidence**,
   and **Classification Status: Classified**. The result is saved to History as before.

Test one photo of each class — Piña, Jusi, and Cocoon. The training photos in
`dataset/pina`, `dataset/jusi`, `dataset/cocoon` (copy a few to the phone) or fresh
close-up photos both work.

## 9. Test the camera

Tap **Camera**.

- **If the camera opens:** point the rear camera at the fabric, adjust **Zoom** if shown,
  tap **Capture**, check the preview, then tap **Classify Textile**.
- **If you see "Camera access may require HTTPS on this device/browser":** this is
  expected on `http://192.168.x.x`. Phone browsers (Chrome on Android, Safari on iPhone)
  only allow live camera access on HTTPS pages or `localhost`. Use
  **Upload from Gallery** instead — on most phones the gallery picker also offers
  "Take photo", which uses the normal camera app (including its own zoom/Pro mode).

### Zoom

When the browser exposes camera zoom, the page requests up to 10x (never more than the
device allows) and shows what was actually applied:

- `Zoom: 10x ✓` — 10x was applied.
- `Maximum supported browser zoom: 5x · Applied: 5x` — the browser allows less than 10x.
- `Browser zoom control unavailable` — the browser/camera doesn't expose zoom.

Browser zoom may be digital cropping and is not the same as your camera app's Pro Mode
optical zoom.

### Optional: live camera on the phone over HTTPS

Only needed if you want the in-page camera instead of the gallery. Two options:

- **Android + USB (easiest):** enable USB debugging, connect the phone, open
  `chrome://inspect/#devices` on the laptop, and add port forwarding for
  `5500 → localhost:5500` and `5501 → localhost:5501`. Then open
  `http://localhost:5500/Frontend/src/pages/index.html` on the phone. `localhost` is
  treated as secure, so the camera works.
- **Chrome flag (Android, testing only):** open
  `chrome://flags/#unsafely-treat-insecure-origin-as-secure` on the phone, add
  `http://<LAPTOP_IP>:5500`, enable, and relaunch Chrome. Remove it after testing.

---

## Troubleshooting

### `http://<LAPTOP_IP>:5501/health` doesn't open on the phone

1. Is Terminal 1 still running, and was it started with `--host 0.0.0.0`?
2. Are both devices on the same Wi-Fi? Some routers block devices from talking to each
   other ("AP isolation" / "client isolation", common on guest networks). Turn it off in
   the router, or use a different network or the laptop's Mobile Hotspot.
3. **Windows Firewall.** Windows usually asks the first time Python listens on the
   network — click **Allow**. Your Wi-Fi is currently set to **Public**, and Windows
   already has an inbound "python.exe" Allow rule for Public networks. If the phone
   still can't connect, make the network **Private** (Settings → Network & internet →
   Wi-Fi → your network → Network profile type → Private) and add a rule that only opens
   the two ports on private networks. Run PowerShell **as Administrator**:

   ```powershell
   New-NetFirewallRule -DisplayName "BarongClassifier LAN test (5500, 5501)" `
       -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5500,5501 `
       -Profile Private
   ```

   Remove it after testing:

   ```powershell
   Remove-NetFirewallRule -DisplayName "BarongClassifier LAN test (5500, 5501)"
   ```

   Do not turn Windows Firewall off.

### The site opens but Classify says "Cannot connect to the classification server"

Port 5500 works but 5501 doesn't: restart Terminal 1 with `--host 0.0.0.0` and check the
firewall step above for port 5501.

### Result page messages

| Message | Meaning |
| --- | --- |
| Classifier unavailable | The phone can't reach port 5501 (server stopped, different Wi-Fi, firewall). |
| Server timeout | The laptop took over 90 s (asleep or very busy). |
| Unsupported image | The file is not a readable JPG/PNG. |
| Invalid image | The photo was empty or damaged. |
| Prediction failed | The CNN hit an error; details are printed in Terminal 1. |

### iPhone HEIC photos

The upload accepts JPG and PNG. iPhone Safari normally converts HEIC photos to JPG when
you pick them from the gallery. If a photo is rejected, set Camera → Formats →
**Most Compatible** on the iPhone.

## Security notes

- Nothing is deployed. Both servers are only reachable on your local network while the
  terminals are open; press `Ctrl+C` in each terminal to stop them.
- The classifier only accepts browser requests from pages opened on `localhost` or a
  private network address (192.168.x.x, 10.x.x.x, 172.16–31.x.x).
- Supabase keeps using the existing public anon key in `Frontend/src/js/supabaseClient.js`.
  No service-role key is used anywhere.
