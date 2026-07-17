# v2 external-evaluation audit

状态：`PASS`。

## Immutable metadata

- mode: `COMPLETE_EXTERNAL_EVALUATION`
- v2_final_policy_sha256: `be320418ce7852ec48ff386dccfa79e9752e914392bfafa8b331cdda14045826`
- external_evaluation_id: `v2_ntp_one_shot_external_evaluation_v1`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. output 文件集合固定且没有样本级 prediction CSV | PASS |
| 2 | 2. NTP candidate identity、独立授权、绑定 hashes 和预先创建的输出锁完整 | PASS |
| 3 | 3. exact/connectivity/tautomer overlap 均为零 | PASS |
| 4 | 4. final artifact、policy 和 member hashes 在 external 后未改变 | PASS |
| 5 | 5. 仅按预注册方式报告 tautomer/scaffold/similarity，AD 不改变 call | PASS |
| 6 | 6. 仅保留 prediction digest，不保留样本级预测 | PASS |
| 7 | 7. external 结果未触发模型或规则修改 | PASS |
| 8 | 8. 所需 aggregate diagnostics、同 covered subset 的 v1 比较和预注册阈值 readout 已记录 | PASS |

本审核只读取 policy、final artifacts 和 future external-evaluation metadata；不读取任何 external split 行。
