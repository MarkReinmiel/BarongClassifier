# Stage A — Implementation & Dataset Audit Report

**Generated:** 2026-10-24  
**Status:** Inspection + source inventory complete. **No model training performed yet** (per mandatory execution order).

> Security note: A `.env` file with live credentials was pasted into chat earlier. Rotate those secrets (DB password, mail app password, Cloudinary, Turnstile, Supabase keys) when practical. This report does not repeat them.

---

## 1. Existing architecture

| Layer | Role |
|--------|------|
| **Frontend/** | Static UI reference (classify, camera, history) |
| **Backend/** | Auth API + optional `machine learning/classify_server.py` |
| **Frontend/src/customer/** | Flask portal (`:5000`) — auth, classify, history |
| **Frontend/src/owner/** | Flask portal (`:5001`) — owner auth, classify, user admin |
| **Supabase Postgres** | Users + `public.classifications` history |
| **dataset/** | Canonical training images + new ZIP archives |

Customer and Owner both load a local Keras CNN (`models/barong_model.keras`) via nearly identical `app/ml/model_loader.py` + `app/ml/predictor.py`. Dataset folders under Customer/Owner are **Windows junctions** to `dataset/{cocoon,jusi,pina}` (not separate copies).

---

## 2. Active model (current working)

| Location | File |
|----------|------|
| Customer | `Frontend/src/customer/models/barong_model.keras` (~21.7 MB) + `labels.json` |
| Owner | `Frontend/src/owner/models/barong_model.keras` + `labels.json` |
| Backend artifacts (source of copy) | `Backend/machine learning/artifacts/barong_mobilenetv2.keras` |

**Class order (labels.json):** `["cocoon", "jusi", "pina"]`  
**Input size:** 224×224 RGB  
**Preprocessing (inference):** PIL open → RGB → LANCZOS resize → `uint8` batch → `model.predict`  
**Architecture:** MobileNetV2 transfer learning (see `train_cnn.py`)

**Baseline metrics** (`Backend/machine learning/artifacts/metrics.json`):

- Test accuracy reported: **1.0** on **39** test images  
- Confusion matrix: diagonal only (13 / 12 / 14)  
- Caution: perfect test accuracy on a small, possibly correlated set is **not** proof of field robustness.

---

## 3. Training & inference entry points

| Purpose | Path |
|---------|------|
| Train (repo dataset) | `Backend/machine learning/train_cnn.py` → writes `artifacts/` |
| Train (Customer junction) | `Customer/scripts/train_cnn.py` → writes `Customer/models/` |
| Copy model + junctions | `Customer/scripts/setup_ml_assets.py` |
| Local HTTP classifier | `Backend/machine learning/classify_server.py` |
| Customer predict | `Customer/app/services/classification_service.py` → `app.ml.predictor.predict` |
| Owner predict | `Owner/app/services/classification_service.py` → same pattern |

Split strategy already groups by capture second (`IMG_YYYYMMDD_HHMMSS`) when filenames match that pattern — good start for leakage control, but **physical-sample IDs are mostly unknown**.

---

## 4. API / UI prediction shape (today)

Customer/Owner return roughly:

```json
{
  "label": "Piña",
  "confidence": 0.96,
  "image_name": "upload.jpg",
  "created_at": "..."
}
```

Owner also returns an inline `image_data_url` for the result page.  
**No hierarchical `main_class` / `variant` fields yet.**  
**Cloudinary keys exist in env but classify does not upload images to Cloudinary.**

---

## 5. Original dataset paths (preserved)

| Path | Images (audit) | Notes |
|------|----------------|-------|
| `dataset/cocoon` | **83** `.jpg` | Original class folder — **do not move/delete** |
| `dataset/jusi` | **100** `.jpg` | Original |
| `dataset/pina` | **94** `.jpg` | Original |
| `Customer/datasets/{cocoon,jusi,pina}` | junctions → above | |
| `Owner/datasets/{cocoon,jusi,pina}` | junctions → above | |
| `barong type/{cocoon,jusi,pina}` | **0** images | Empty folders |

**Total original class images:** 277

---

## 6. New ZIP sources found (actual names)

Located under `dataset/` (not pre-extracted folders named exactly `piña 2`, etc.):

| Archive (actual filename) | Images in ZIP | Top-level folder(s) inside ZIP | Provisional label |
|---------------------------|---------------|--------------------------------|-------------------|
| `cocoon-2.zip` | 13 | `cocoon/` | cocoon |
| `Jusi 2.zip` | 24 | `Jusi 2/` | jusi |
| `Piña 2.zip` (encoding may show as `Pi�a 2.zip`) | 18 | `Piña 2/` | pina |
| `piña 2.1.zip` | 14 | `piña pure/` | pina (folder says “pure”) |
| `piña silk.zip` | 34 | `Piña Silk/` + `piña-silk/` | **pina_silk (UNVERIFIED)** |

**ZIP image total:** 103  
Originals + ZIPs remain untouched; extraction (if run) goes only to `ml/data/staging/`.

---

## 7. Label-validation findings (critical)

1. **Folder / ZIP names are provisional only** — not laboratory proof of textile identity.  
2. **`piña silk.zip` must be manually verified** as Piña Silk vs ordinary Piña / Jusi / Cocoon / other. Until verified, those images must **not** silently train a variant class.  
3. **`piña 2.1` extracts as `piña pure`** — treat as candidate **main Piña**, not silk, unless an expert says otherwise.  
4. **Physical sample IDs:** not available in manifests. Many camera-capture filenames lack `IMG_*` grouping. Independent test-set claims will be **limited**.  
5. **No `not_barong` / negative class** exists in the current 3-way softmax.

---

## 8. Risks & missing information

| Risk | Detail |
|------|--------|
| Duplicate / near-duplicate photos | Likely across original + ZIP expansions; need hash audit after staging |
| Data leakage | Same fabric shot many times; random image split would overstate accuracy |
| Perfect baseline metrics | 39-image test / 1.0 accuracy may not generalize |
| Hierarchical API | Frontend/history schema not yet extended for variants |
| Dual portals | Customer + Owner each hold a model copy; updates must sync both + keep backups |
| Cloudinary | Not wired; images are not persisted to Cloudinary on classify |

---

## 9. What was created in this stage

- `ml/` scaffolding: `data/staging`, `reports`, `scripts`, `models/{backups,active,manifests}`
- `ml/scripts/stage_a_zip_inventory.py` — inventory + optional safe extract to staging
- This report: `ml/reports/STAGE_A_IMPLEMENTATION_AND_AUDIT.md`
- Machine inventory JSON (after script run): `ml/reports/source_inventory.json`

**Not done yet (by design):** prepared training trees, manifests with splits, retraining, hierarchical inference, frontend variant UI.

---

## 10. Training readiness (Stage C preview) — STOP before train

| Classifier | Enough verified independent data? | Decision |
|------------|-----------------------------------|----------|
| Main 3-class (pina/jusi/cocoon) | Originals exist; new ZIPs are **provisional** until QA | Can prepare after duplicate audit; train only after Stage B manifest |
| Piña variant (pina vs pina_silk) | Silk ZIP = 34 images, **label verification pending** | **Do not train variant model** until silk images are manually confirmed |

### Decision needed from you

1. Confirm whether images inside `piña silk.zip` are **verified Piña Silk** (yes / no / mixed — which files).  
2. Confirm whether `piña 2` / `piña 2.1` (`piña pure`) should be treated as ordinary **Piña** for the main classifier.  
3. After that, proceed Stage B → then train main (and optionally variant) and deploy copies to **both** `Customer/models` and `Owner/models` with backups.

Per your request to “train in both Customer and Owner”: that means **one training run → backup old models → copy the new artifact into both portals** (they already share the same dataset junctions). Training will not start until Stages B–C clear the gates above.
