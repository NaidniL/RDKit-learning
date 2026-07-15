# v1 post-hoc external diagnostics audit

状态：`PASS`。

## Immutable metadata

- authorization_sha256: `6e1e67d241d56816dd4a564bcad281a56df2872568afe7ea4d2db784c02ab97d`
- final_training_manifest_sha256: `8bd0f85e8f5a8309f534beb2247f4513fb656dfd374fdbcb50b164aabaaa3f5b`
- final_evaluation_manifest_sha256: `c0ce7a90cdf2d3ff966d7490b99af643ce4f9e10b91526fbec29992c47ba25bd`
- dataset_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- external_prediction_digest: `8b82d1dd93f9da4dd2c9ec55b19f0b7b47d3522dfc814b2f2915e8ceda4b3f5e`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 授权是 canonical JSON，且明确禁止模型变更与 prediction CSV | PASS |
| 2 | 授权绑定到当前 final training 与 final external manifests | PASS |
| 3 | 诊断 manifest 绑定同一授权与冻结 manifests | PASS |
| 4 | release id 与 dataset manifest 保持训练冻结版本 | PASS |
| 5 | external split metadata 与 release 及最终外测一致 | PASS |
| 6 | 455 samples、固定 threshold 0.5，且聚合 confusion 精确复现 | PASS |
| 7 | prediction digest 被复现且未写样本级 artifact | PASS |
| 8 | 模型、预处理与 feature manifest 均与 final artifact 相同 | PASS |
| 9 | 诊断目录仅含允许的聚合输出，且没有 CSV | PASS |
| 10 | 一次性目录锁在 external access 前，且脚本无训练或调参调用 | PASS |
| 11 | 诊断输出显式维持 descriptive-only、model-change 与 CSV 禁止状态 | PASS |

本审核只读取授权文件、已有 manifests、诊断聚合报告和脚本；不读取任何 external split 行。
该诊断曾在显式一次性授权下打开 primary external 以产生聚合描述，不能用于 v1 模型选择、调参或阈值修改。
