# v2 validation applicability-domain diagnostic

状态：`POST HOC, DEVELOPMENT ONLY`。

每个 fixed-validation 化合物按其到 train 的最大 ECFP4 Tanimoto similarity 分桶。性能来自冻结的 LightGBM + descriptors train-fit model；该报告不读取 external，也不定义或修改任何 final-evaluation policy。

## Locked inputs

- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- train / validation: `736 / 185`
- model: `lightgbm_descriptors` from `consensus_v2_development_v1.json`
- threshold: `0.5`

## Similarity-stratified validation result

| Max ECFP4 Tanimoto bin | Samples | Mean similarity | AUROC | MCC | Accuracy | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---:|---|
| 0.85+ | 4 | 0.960000 | null | 0.000000 | 1.000000 | 0 / 0 / 0 / 4 |
| 0.70-0.85 | 13 | 0.742160 | 0.800000 | 0.507093 | 0.692308 | 3 / 0 / 4 / 6 |
| 0.50-0.70 | 59 | 0.576983 | 0.843750 | 0.434028 | 0.711864 | 21 / 11 / 6 / 21 |
| <0.50 | 109 | 0.349340 | 0.707893 | 0.314454 | 0.669725 | 47 / 19 / 17 / 26 |

## Interpretation boundary

- These bins are descriptive development diagnostics, not a calibrated applicability-domain threshold or a v1 external analysis.
- A v2 domain policy must be fixed before a separately authorized final evaluation; this result cannot be used to reopen v1.
