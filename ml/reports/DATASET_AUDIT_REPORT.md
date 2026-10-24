# Dataset audit report (Stage B)

**Date:** 2026-10-24  
**Decisions applied:** Piña Silk MIXED/unverified (review only); pia_2 + pia_2.1 accepted as ordinary Piña; main retrain only; no deploy until activation.

## Sources preserved (unchanged)

| Source | Role |
|--------|------|
| `dataset/cocoon`, `dataset/jusi`, `dataset/pina` | Original class folders |
| `dataset/*.zip` | Expansion archives |
| `ml/data/staging/*` | Extracted copies of ZIPs |

## Prepared main dataset

Path: `ml/data/main_classifier/{cocoon,jusi,pina}/` (copies only).

| Class | Prepared images |
|-------|-----------------|
| cocoon | 96 (83 original + 13 cocoon-2) |
| jusi | 124 (100 original + 24 Jusi 2) |
| pina | 126 (94 original + 18 pia_2 + 14 pia_2.1) |
| **Total trainable** | **346** |

Exact sha256 duplicates excluded from training: **0** found among main candidates.

## Splits (group-aware; seed=42)

| Split | cocoon | jusi | pina | total |
|-------|--------|------|------|-------|
| train | 66 | 85 | 87 | 238 |
| val | 14 | 19 | 19 | 52 |
| test | 16 | 20 | 20 | 56 |

Unique groups per split/class are recorded in `prepare_main_summary.json`.

**Limitation:** `physical_sample_id` is mostly unknown. Groups use `IMG_*` capture stems when present, otherwise filename stems. This reduces some leakage but is **not** true physical-sample identity.

## Piña Silk

| Item | Value |
|------|-------|
| Staged images | 34 |
| Verification | **needs_manual_verification** (user: MIXED / NOT FULLY VERIFIED) |
| Used in main train | **No** |
| Used in variant train | **No** (variant not trained) |
| Manifest | `ml/reports/review_required.csv` |

## Artifacts

- `ml/reports/source_manifest.csv`
- `ml/reports/review_required.csv`
- `ml/reports/prepare_main_summary.json`
- `ml/reports/source_inventory.json`
