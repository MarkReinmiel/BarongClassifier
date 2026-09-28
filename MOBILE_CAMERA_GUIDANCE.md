# Mobile camera capture guidance

The in-page camera on **Classify** shows a rectangular guide over the live preview. It
turns **red**, **yellow** or **green**, with a checklist and one main instruction, and
the **Capture Image** button only works when the guide is green.

The guidance only checks whether the *photo conditions* look like the training photos.
**Green does not mean the fabric is Barong, Piña, Jusi or Cocoon.** The existing CNN
still makes the prediction, exactly as before.

It does **not** measure physical distance. There is no depth sensor or known-size
reference, so it never shows centimetres. "Move closer" and "Move slightly farther" are
based on how large the weave looks in the image.

Files involved:

| File | Role |
| --- | --- |
| `Frontend/src/js/cameraGuidance.js` | Thresholds (`CAMERA_GUIDANCE_CONFIG`) and the image analysis |
| `Frontend/src/js/classify.js` | Camera, guide overlay, checklist, capture / retake, zoom |
| `Frontend/src/pages/classify.html`, `Frontend/src/css/classify.css` | Markup and styles |
| `Backend/machine learning/calibrate_camera_guidance.py` | Measures the same values on `dataset/` to pick thresholds |

## What is measured

About 5 times per second (`ANALYSIS_INTERVAL_MS: 200`), only the part of the video
**inside the guide** is shrunk to 224×224 (the CNN's input size) and converted to
brightness. The analysis runs in the browser on the phone; nothing is uploaded while
aiming. All checks use that 224×224 grey image:

| Check | How | Messages |
| --- | --- | --- |
| **Framing / coverage** | The guide is split into a 4×4 grid. A cell counts as textile if its edge detail is at least 45% of the stronger cells (and above a small minimum). | "Move closer" when too much of the guide is empty |
| **Distance (texture scale)** | Edge strength of the image is compared with the same image at half size. Small, fine texture loses most of its detail when halved (low score = too far); large, coarse texture keeps it (high score = too close). | "Move closer", "Adjust distance — slightly closer / farther", "Good distance", "Move slightly farther" |
| **Sharpness** | Variance of the Laplacian (a standard focus measure; blur lowers it). | "Image blurry — hold steady", "Image slightly soft — hold steady", "Focus OK" |
| **Lighting** | Average brightness, 0–255. | "Too dark — improve lighting", "Lighting is dim — add light", "Very bright — reduce light", "Too bright — reduce glare", "Lighting OK" |
| **Glare** | Share of almost-white pixels (≥ 250). Advisory only, never blocks capture. | "Reduce glare / change angle" |
| **Stability** | Difference between a 28×28 thumbnail of this frame and the previous one, relative to texture strength, smoothed over the last 5 frames. Normal hand tremor is allowed; it blocks when the camera moves off the fabric. Must stay stable for 0.2 s. | "Hold steady", "Hold steady…", then green |

## Red / yellow / green

Each check is **✓ good**, **△ adjust** or **✕ bad**:

- **Red** — any check is bad. The headline shows the most important problem, in this
  order: lighting, focus, distance, stability. If there is no textile detail at all,
  distance comes before focus, so the message is "Point at the textile and hold steady".
- **Yellow** — nothing is bad but something needs a small adjustment. Order: distance,
  lighting, focus, stability. This includes the 0.7 s "Hold steady…" hold.
- **Green** — every check is good: "Ready to capture". Capture is enabled.

Glare only adds a warning to the checklist and never changes the colour.

## Thresholds (all in `CAMERA_GUIDANCE_CONFIG`)

Values were measured on all 277 photos in `dataset/` with the same browser code that
runs on the phone. The defaults are deliberately relaxed (less sensitive) and the
distance band asks for a closer shot than the training photos:

| Setting | Default | Why |
| --- | --- | --- |
| `SCALE_GOOD_MIN` / `SCALE_GOOD_MAX` | 0.53 / 0.88 | Closer than training (p1 0.461, median 0.546, p99 0.715). Photos simulated 1.4× closer ≈ 0.67, 2× ≈ 0.79, 3× ≈ 0.82–0.91 |
| `SCALE_ADJUST_MIN` / `SCALE_ADJUST_MAX` | 0.45 / 0.95 | Red below / above |
| `SHARPNESS_GOOD_MIN` / `SHARPNESS_MIN` | 40 / 20 | Lowest training photo (cocoon) p1 ≈ 86; live video is softer than photos |
| `BRIGHTNESS_DIM` / `BRIGHTNESS_BRIGHT` | 90 / 225 | Training photos are 168–181 |
| `BRIGHTNESS_DARK` / `BRIGHTNESS_TOO_BRIGHT` | 60 / 245 | Red limits |
| `COVERAGE_GOOD_MIN` / `COVERAGE_ADJUST_MIN` | 0.75 / 0.5 | At most 4 / 8 empty cells out of 16 |
| `TEXTURE_MIN` | 5 | Below this there is no fabric detail (blank wall, very blurry) |
| `GLARE_WARN` | 0.02 | Warn when > 2% of pixels are almost white |
| `MOTION_STABLE_MAX` / `MOTION_HIGH` | 1.0 / 2.0 | On close-up fabric any hand tremor or pan reads ≈ 0.5–0.8, pointing away from the fabric reads 2–33. Only large movements block; shake blur is caught by the sharpness check |
| `MOTION_SMOOTHING_FRAMES` | 5 | Stability uses the median of the last 5 readings, so one jumpy frame is ignored |
| `STABLE_HOLD_MS` | 200 | How long it must stay stable before green |

Other options: `ANALYSIS_INTERVAL_MS`, `GUIDE_ASPECT` (3:4), `CROP_TO_GUIDE`,
`INITIAL_ZOOM`, `MAX_REQUESTED_ZOOM` (10), `CALIBRATION_MODE_ALLOWED`.

After changing `cameraGuidance.js`, bump `?v=` on its `<script>` tag in `classify.html`
so the phone doesn't use a cached copy.

## Calibration

### 1. From the training photos (laptop)

```powershell
python "Backend/machine learning/calibrate_camera_guidance.py"
```

It measures every photo in `dataset/` the same way as the browser (same staged shrink
to 224×224), prints per-class percentiles, simulates the photos closer and farther, and
prints suggested threshold values. Run it again if the dataset changes.

### 2. On the phone (Calibration Mode, development only)

Open `.../Frontend/src/pages/classify.html?calibrate=1` and start the camera. A small
panel on the preview shows the live coverage, scale, sharpness, brightness, glare and
motion values next to their thresholds, plus video resolution, guide size in pixels and
analysis time. In this mode **Capture is always enabled**, so you can also take photos
the guide would reject.

Suggested procedure: hold the phone the way the training photos were taken (fabric
filling the frame, sharp, even light). Note the scale and sharpness values for each
fabric, then move closer and farther and note where the photos stop looking like the
training data. Put those values into `CAMERA_GUIDANCE_CONFIG`.

To remove Calibration Mode completely, set `CALIBRATION_MODE_ALLOWED: false`. Then
`?calibrate=1` does nothing.

### Changing the target distance

The "good distance" is the `SCALE_GOOD_MIN`–`SCALE_GOOD_MAX` band. Raise both values to
make users hold the phone closer, lower them to allow farther. Keep the `ADJUST` values
a little outside the good band so there is a yellow zone between green and red.

## From capture to the CNN

1. **Capture Image** takes the current full-resolution video frame. The camera requests
   up to 2560×1440 from the rear camera; the phone picks the nearest mode it supports.
2. With `CROP_TO_GUIDE: true` only the area inside the guide is kept (a 3:4 image), and
   saved as a JPEG (quality 0.92).
3. The camera stops and the photo appears in **Image Preview** with **Retake** and
   **Analyze Textile**.
4. **Analyze Textile** uses the same path as gallery uploads: the image is stored in
   IndexedDB, the Result page sends it to the existing `POST /predict` on the laptop,
   and the unchanged CNN preprocessing (RGB → 224×224 LANCZOS) and model make the
   prediction. Class names and order are unchanged.

### Why crop to the guide

The training photos show only fabric, in a 3:4 / 4:3 frame. The full camera frame also
contains the table, hand or background around the fabric, and is 16:9, so it would be
squashed when resized to 224×224. The guide area is exactly what the guidance checked,
so cropping sends the CNN an image closer to its training data. Set
`CROP_TO_GUIDE: false` to send the whole frame instead.

## Zoom

If the browser exposes camera zoom, the zoom controls let you request up to 10×, clamped
to what the device reports. The page shows what was actually applied. It never pretends
to zoom further. Browser zoom is often digital (cropping), which lowers real detail;
the sharpness check will reflect that.

## Performance and cleanup

- Analysis runs on a ~224×224 image every 200 ms (about 25 ms per analysis on the laptop
  webcam). It pauses when the page is hidden and stops when the camera closes.
- The camera stream stops on Capture, Close Camera, leaving the page, and page hide.

## Limitations

- **No physical distance.** Distance guidance is from texture size in the image only.
- **Fabric-dependent scale.** Cocoon's weave looks larger than Jusi's or Piña's at the
  same distance (training medians ≈ 0.65 vs 0.49 / 0.55). One band has to fit all three
  fabrics, so Cocoon held too far away may show only yellow, and Jusi / Piña a little
  too close may still show green.
- **Blur and scale interact.** Blur removes fine detail, which also looks like "large
  texture". This is why focus is reported before distance.
- **Live video is softer than still photos**, and phone processing (sharpening, noise
  reduction) changes the numbers. The sharpness limits are deliberately lower than
  the training photo values.
- **Background texture** (patterned tablecloth, carpet) can count as coverage.
- **Glare detection** only sees clipped white pixels, not softer reflections.
- **Not yet calibrated on the real phone.** Defaults come from the training photos and
  laptop webcam tests. Use Calibration Mode on the phone and adjust if green is too
  hard or too easy to reach.
