# v1 primary external similarity and scaffold stratified metrics

状态：`COMPLETE — DESCRIPTIVE ONLY`。

## Maximum ECFP4 Tanimoto similarity to train

| Bin | Samples | Mean similarity | AUROC | MCC | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---|
| 0.85+ | 5 | 0.988235 | 1.000000 | 1.000000 | 1 / 0 / 0 / 4 |
| 0.70-0.85 | 19 | 0.773066 | 1.000000 | 0.724569 | 3 / 2 / 0 / 14 |
| 0.50-0.70 | 112 | 0.582997 | 0.773159 | 0.347919 | 26 / 21 / 14 / 51 |
| <0.50 | 319 | 0.326778 | 0.667393 | 0.229184 | 100 / 46 / 79 / 94 |

## Murcko scaffold support relative to train

| Status | Samples | AUROC | MCC | TN / FP / FN / TP |
|---|---:|---:|---:|---|
| scaffold_seen | 142 | 0.704108 | 0.200148 | 43 / 18 / 41 / 40 |
| scaffold_novel_or_empty | 313 | 0.731967 | 0.333044 | 87 / 51 / 52 / 123 |
