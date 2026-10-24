# Piña Variant Model Training Report (Provisional)

**Version:** variant_20261024_153608
**Artifact:** C:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier\ml\models\variant\active\barong_pina_variant.keras

## Test metrics

- Accuracy: **0.6451612903225806**
- Macro F1: **0.5163120567375886**
- N test: **31**
- Confusion matrix (order ['pina', 'pina_silk']): [[18, 0], [11, 2]]

## Per-class (test)

{
  "pina": {
    "precision": 0.6206896551724138,
    "recall": 1.0,
    "f1": 0.7659574468085106,
    "support": 18
  },
  "pina_silk": {
    "precision": 1.0,
    "recall": 0.15384615384615385,
    "f1": 0.26666666666666666,
    "support": 13
  }
}

**Acceptance threshold:** 0.800000011920929

## Limitations

- Provisional: only 2 Piña Silk physical samples.
- Test silk sample differs from train silk sample but diversity is tiny.
- Retrain when ~150 images across many distinct silk textiles arrive.

150 more photos help only if from many different Piña Silk textiles.