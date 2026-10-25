# Relevance / OOD Gate Evaluation (Experimental)

**Version:** `relevance_20261025_154859`
**Method:** `hybrid_centroid_msp_quality`
**Model (unchanged):** `ml/models/active/main_classifier.keras`

## Selected method

1. Image quality (brightness + Laplacian variance).
2. Cosine distance from MobileNetV2 penultimate features to class centroids (train).
3. Softmax max-probability / entropy as secondary soft checks.

No paid vision API. Production textile CNN weights were not retrained.

## Limitations (read before trusting metrics)

- Synthetic OOD only (noise/solids/gradients); not a curated unrelated-photo set.
- False-acceptance rates on real-world OOD (faces, cars, other fabrics) are unknown.
- Centroid distance can reject unusual textile crops that differ from train framing.
- Softmax confidence is a secondary signal only; it is not trusted alone for OOD.

## Thresholds (tuned on VAL; frozen for TEST)

- `max_centroid_distance`: **0.477**
- `uncertain_centroid_distance`: **0.35775**
- `min_softmax_confidence`: **0.45**
- `min_laplacian_var`: **80.0**

## Held-out TEST (synthetic OOD)

- ID false-rejection rate: **0.036**
- Synthetic OOD false-acceptance rate: **0.000**
- Approx feature forward latency: **92.8 ms**

These OOD figures are **not** real-world unrelated photo rates.

## Confusion matrix (TEST textiles accepted by gate)

`[[15, 1, 0], [0, 19, 0], [1, 0, 18]]`

Per-class report JSON is in `relevance_gate_metrics.json`.
