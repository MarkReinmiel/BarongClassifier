# Piña Silk provisional pipeline summary

**Date:** 2026-10-24  
**Variant version:** `variant_20261024_153608`  
**Main 3-class model:** unchanged

## What was done

1. Label review completed (34 verified `pina_silk`, 2 physical samples).
2. Variant dataset prepared: 102 ordinary Piña + 34 Piña Silk (sample-grouped splits).
3. Provisional binary MobileNetV2 trained and activated into Customer / Owner / Backend.
4. Apps call the variant model only when main class is Piña; Jusi/Cocoon skip it.
5. Hardcoded permanent `undetermined` replaced with real variant output (or uncertain when below threshold).

## Test metrics (honest)

| Metric | Value |
|---|---|
| Test accuracy | **64.5%** |
| Macro F1 | **0.52** |
| Ordinary Piña recall | 100% (18/18) |
| Piña Silk recall | **15% (2/13)** |
| Confusion | silk often predicted as ordinary Piña |

Acceptance threshold: **0.80** (conservative — many silk calls will show “Undetermined” until data improves).

## About ~150 more Piña Silk photos

**Yes, 150 is a good target** — **if** they come from many different Piña Silk textiles (different barongs/fabrics), not 150 shots of the same cloth.

Recommended: ~10–20 distinct pieces × several photos each ≈ 150.

Then re-run:

```text
python ml/scripts/stage1_pina_silk_label_review.py
# fill/verify CSV
python ml/scripts/prepare_variant_dataset.py
python ml/scripts/train_variant_classifier.py
python ml/scripts/activate_variant_to_apps.py
```

## Rollback

Main model untouched. To disable variant: remove `*/models/barong_pina_variant.keras` (apps fall back to undetermined message).
