# Main classifier training report

- Version: `main_20261104_132046`
- Artifact: `C:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier\ml\models\active\main_classifier.keras`
- Test accuracy: **0.984** on 62 images
- Train / val / test images: 261 / 57 / 62
- Piña Silk variant: **retired** — silk images folded into Piña.
- Deployed to Customer/Owner: **no** (pending activation gate).

## Classification report
```
              precision    recall  f1-score   support

      Cocoon      1.000     0.938     0.968        16
        Jusi      1.000     1.000     1.000        20
        Piña      0.963     1.000     0.981        26

    accuracy                          0.984        62
   macro avg      0.988     0.979     0.983        62
weighted avg      0.984     0.984     0.984        62

```

## Confusion matrix (rows=true, cols=pred; cocoon,jusi,pina)
```
[[15, 0, 1], [0, 20, 0], [0, 0, 26]]
```

## Limitations
- physical_sample_id mostly unknown; splits use filename/IMG groups.
- pia_2 / pia_2.1 included under user provisional acceptance.
- Former pia_silk / pina_silk images trained as Piña.