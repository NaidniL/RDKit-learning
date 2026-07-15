# Final external evaluation audit

状态：`PASS`。

## Immutable metadata

- external_evaluation_id: `EXT:fa289ad9ac127734`
- model_training_manifest_sha256: `8bd0f85e8f5a8309f534beb2247f4513fb656dfd374fdbcb50b164aabaaa3f5b`
- dataset_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset_manifest_sha256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- external_split_sha256: `5070aa855385795106e4c45c3f74dc6616ba11d912ec017d729f2ec09dc12714`
- external_prediction_digest: `8b82d1dd93f9da4dd2c9ec55b19f0b7b47d3522dfc814b2f2915e8ceda4b3f5e`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. external evaluation 状态为 COMPLETE | PASS |
| 2 | 2. model training manifest hash 与 final artifact manifest 一致 | PASS |
| 3 | 3. dataset release 和 dataset manifest hash 与训练冻结时一致 | PASS |
| 4 | 4. external split hash 与 release manifest 一致 | PASS |
| 5 | 5. samples = 455 | PASS |
| 6 | 6. threshold = 0.5 | PASS |
| 7 | 7. 模型、特征、预处理、阈值均未在 external 后改变 | PASS |
| 8 | 8. 未写 external prediction CSV | PASS |
| 9 | 9. prediction digest 已记录 | PASS |
| 10 | 10. external-final repeat lock 生效 | PASS |
| 11 | 11. 当前 Git diff 只包含预期报告、manifest、lock 文件 | PASS |
| 12 | 12. external 结果没有回流到模型选择或调参代码 | PASS |

本审核只读取既有 final artifact、external evaluation、release 元数据与 Git 元数据；不读取任何 external split 行。
