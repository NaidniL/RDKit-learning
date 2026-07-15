# Final external evaluation v1

状态：`COMPLETE`。primary external 仅评估一次；未改动模型、特征、预处理或阈值。

## Locked inputs

- model training manifest SHA-256: `8bd0f85e8f5a8309f534beb2247f4513fb656dfd374fdbcb50b164aabaaa3f5b`
- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- external split SHA-256: `5070aa855385795106e4c45c3f74dc6616ba11d912ec017d729f2ec09dc12714`
- samples: `455`
- threshold: `0.5`

## Aggregate metrics

| Metric | Value |
|---|---:|
| auroc | 0.719437 |
| auprc | 0.772798 |
| accuracy | 0.643956 |
| balanced_accuracy | 0.644993 |
| precision | 0.702586 |
| recall | 0.636719 |
| f1 | 0.668033 |
| brier | 0.244842 |
| log_loss | 0.759712 |
| sensitivity | 0.636719 |
| specificity | 0.653266 |
| mcc | 0.287757 |

## Confusion counts

- true_negative: `130`
- false_positive: `69`
- false_negative: `93`
- true_positive: `163`

未写出 external prediction 文件；仅在 manifest 记录 canonical prediction digest。
