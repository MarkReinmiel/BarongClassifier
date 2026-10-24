# Main classifier training report

- Version: `main_20261024_131505`
- Artifact: `C:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier\ml\models\active\main_classifier.keras`
- Test accuracy: **0.964** on 56 images
- Train / val / test images: 238 / 52 / 56
- Variant (Piña Silk) model: **not trained** (labels unverified).
- Deployed to Customer/Owner: **no** (pending activation gate).

## Classification report
```
              precision    recall  f1-score   support

      Cocoon      0.938     0.938     0.938        16
        Jusi      0.952     1.000     0.976        20
        Piña      1.000     0.950     0.974        20

    accuracy                          0.964        56
   macro avg      0.963     0.963     0.962        56
weighted avg      0.965     0.964     0.964        56

```

## Confusion matrix (rows=true, cols=pred; cocoon,jusi,pina)
```
[[15, 1, 0], [0, 20, 0], [1, 0, 19]]
```

## Limitations
- physical_sample_id mostly unknown; splits use filename/IMG groups.
- pia_2 / pia_2.1 included under user provisional acceptance.
- pia_silk excluded from all training.