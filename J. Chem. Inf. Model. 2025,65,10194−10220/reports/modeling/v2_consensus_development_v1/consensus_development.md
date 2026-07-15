# v2 development-only consensus experiment

状态：`COMPLETE — DEVELOPMENT ONLY`。

本报告固定三模型与 unanimity/inconclusive 规则后，只在 train fit 和 fixed validation 评估一次。它没有读取 external，也没有写出样本级预测。

## Consensus result on fixed validation

- coverage: `0.724324` (134 / 185)
- inconclusive: `0.275676` (51 / 185)
- covered-set MCC: `0.525774`
- covered-set accuracy: `0.761194`
- covered confusion (TN / FP / FN / TP): `58 / 11 / 21 / 44`

## Individual fixed-validation results

| Model | Features | AUROC | AUPRC | MCC |
|---|---:|---:|---:|---:|
| lightgbm_descriptors | 220 | 0.765912 | 0.789603 | 0.380601 |
| random_forest_maccs | 167 | 0.751532 | 0.763637 | 0.388306 |
| random_forest_ecfp4 | 2048 | 0.710632 | 0.726311 | 0.385403 |

该 development result 不能用于修改已封存的 v1，也不授权任何 external evaluation。任何 v2 final evaluation 需要新的、单独冻结的 final artifact 和评估协议。
