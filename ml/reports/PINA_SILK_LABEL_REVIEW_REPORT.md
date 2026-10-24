# Piña Silk Label Review Report (Stage 1) — COMPLETED

**Updated (UTC):** 2026-10-24T15:24:58.249611+00:00
**Reviewer:** Owner-delegated (assistant filled CSV at user request after visual QC)

## Counts after labeling

- Total rows: **34**
- Verified: **34**
- Verified pina_silk: **34**
- Verified pina / other / uncertain: **0**
- Independent physical-sample IDs assigned: **2** → {'phys_silk_cam_01': 21, 'phys_silk_img_01': 13}

## Sample grouping (leakage control)

| physical_sample_id | images | notes |
|---|---|---|
| phys_silk_cam_01 | 21 | All camera-capture-* — near-identical burst from one session |
| phys_silk_img_01 | 13 | All IMG_* consecutive shoot — treated as one sample until owner splits further |

## Adequacy gate for Stage 2 variant training

- Verified Piña Silk images: **34**
- Independent silk physical samples: **2**
- Ordinary Piña for binary head: not yet counted from main/pina staging (available in main dataset)

**GATE: INADEQUATE diversity for a reliable Piña vs Piña Silk classifier.**

With only **2** independent silk samples, any train/val/test split will either leak
(same sample in multiple splits) or leave a split with zero silk diversity.
Production should keep variant=undetermined until more verified silk textiles are captured
(recommend ≥6–10 distinct physical Piña Silk samples, several photos each).

Stages 2–7 remain **blocked** for deployment-quality training.

## Caveats

- Labels are **not** from a textile laboratory; they are owner-intent + visual fabric QC.
- If any image is ordinary Piña or another fiber, re-open that row to other/pina/excluded.

- Manifest: c:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier\ml\reports\pina_silk_label_review.csv
- Contact sheet: ml/reports/pina_silk_contact_sheet.jpg