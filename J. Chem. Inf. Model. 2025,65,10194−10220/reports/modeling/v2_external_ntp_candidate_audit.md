# v2 NTP candidate-external audit

状态：`PASS`。

## Immutable metadata

- candidate_rows: `49`
- class_counts: `{'carcinogen': 15, 'noncarcinogen': 34}`
- candidate_release_manifest_sha256: `3308acd324980561918850a91b1451e4d556cc59e0f024125f64b3c0b6e5b3b2`
- formal_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- mode: `CANDIDATE_PRE_EXTERNAL_AUTHORIZATION`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. 冻结配置、来源和不复用 v1 CCRIS 的边界完整 | PASS |
| 2 | 2. raw source、acquisition manifest 和 candidate CSV hashes 均已绑定 | PASS |
| 3 | 3. candidate 标签均来自冻结的 P/no-NE 或 all-NE/NT 规则，且两类均存在 | PASS |
| 4 | 4. 与 formal development 的 exact/connectivity/tautomer overlap 均为零 | PASS |
| 5 | 5. candidate 仍未获 external evaluation 授权，且没有任何 evaluation output | PASS |

本审核读取 NTP candidate 与 development 结构标识用于重叠审计；不载入 v1 CCRIS external，不进行推断或写入预测。
