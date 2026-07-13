# Final config independent audit

状态：`PASS`。

## Immutable metadata

- HEAD: `846cf64127783c94806a5622ce9e7b246ecea9fb`
- dataset_release_manifest_sha256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- policy_sha256: `e56583f94f71326fce2d59f63c4027b18445403b27c18eddfc141881cd5cdc10`
- config_sha256: `19a0ca3d720c940e6574b43abfee13a6f7ca76f73d67b13ef60b7844fef6f486`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. final config SHA-256 固定值 | PASS |
| 2 | 2. final config canonical JSON | PASS |
| 3 | 3. selection report 存在且 policy hash 匹配 | PASS |
| 4 | 4. modeling policy hash 匹配 | PASS |
| 5 | 5. proposed final config 是 LightGBM + descriptors | PASS |
| 6 | 6. selected params 与排序第 1 名一致 | PASS |
| 7 | 7. threshold 固定为 0.5 | PASS |
| 8 | 8. final refit 固定为 train+validation | PASS |
| 9 | 9. config external 仍锁定 | PASS |
| 10 | 10. 所有 experiment manifest external_access=denied | PASS |
| 11 | 11. 不存在 external metric/prediction/digest/artifact | PASS |
| 12 | 12. 未发现候选外模型、特征或扩展网格 | PASS |
| 13 | 13. 当前 Git diff 仅含预期路径 | PASS |
| 14 | 14. HEAD/release/policy/config hashes 已写入报告 | PASS |

本脚本只读校验输入；唯一写入为本报告。external 未被读取或解锁。
