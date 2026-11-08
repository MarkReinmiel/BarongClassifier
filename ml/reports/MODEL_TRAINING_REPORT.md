# Main classifier training report

- Version: `main_20261108_063110`
- Artifact: `C:\Users\louis\OneDrive\Documents\GitHub\BarongClassifier\ml\models\active\main_classifier.keras`
- Test accuracy: **0.933** on 135 images
- Train / val / test images: 630 / 135 / 135
- Data source: balanced folders (300/class)
- Piña Silk variant: **retired** — silk images folded into Piña.
- Deployed to Customer/Owner: **no** (pending activation gate).

## Classification report
```
              precision    recall  f1-score   support

      Cocoon      0.913     0.933     0.923        45
        Jusi      0.977     0.956     0.966        45
        Piña      0.911     0.911     0.911        45

    accuracy                          0.933       135
   macro avg      0.934     0.933     0.933       135
weighted avg      0.934     0.933     0.933       135

```

## Confusion matrix (rows=true, cols=pred; cocoon,jusi,pina)
```
[[42, 1, 2], [0, 43, 2], [4, 0, 41]]
```

## Limitations
- physical_sample_id mostly unknown; splits use filename/IMG groups.
- pia_2 / pia_2.1 included under user provisional acceptance.
- Former pia_silk / pina_silk images trained as Piña.