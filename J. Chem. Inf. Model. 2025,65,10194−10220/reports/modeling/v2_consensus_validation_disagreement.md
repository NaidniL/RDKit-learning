# v2 validation disagreement and error-complementarity diagnostic

状态：`POST HOC, DEVELOPMENT ONLY`。

本报告按冻结的 v2 config 重现 train fit / fixed validation predictions，并仅输出聚合的模型分歧与错误重叠统计。它不保存样本级 prediction，不读取 external，且不改变 candidate、parameter、threshold 或 consensus rule。

## Locked inputs

- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- validation samples: `185`
- threshold: `0.5`

## Pairwise agreement and error overlap

| Pair | Class agreement | Both correct | Only first wrong | Only second wrong | Both wrong | Error Jaccard |
|---|---:|---:|---:|---:|---:|---:|
| lightgbm_descriptors / random_forest_maccs | 148 | 110 | 19 | 18 | 38 | 0.506667 |
| lightgbm_descriptors / random_forest_ecfp4 | 148 | 110 | 19 | 18 | 38 | 0.506667 |
| random_forest_maccs / random_forest_ecfp4 | 157 | 115 | 14 | 14 | 42 | 0.600000 |

## Unanimity rule summary

- unanimous calls: `134`
- unanimous correct: `102`
- unanimous wrong: `32`
- inconclusive due to disagreement: `51`

A nonzero count in either ‘only ... wrong’ column is evidence that the two fixed models do not make identical validation errors. This is descriptive evidence for the predeclared consensus research question, not permission to select a different rule after seeing validation.
