# v2 development-only consensus audit

状态：`PASS`。

## Immutable metadata

- config_sha256: `d6beda993b141750e254cd869e8451a444e92e14d9fb97f24b3d80cd865485f3`
- dataset_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset_manifest_sha256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- consensus_coverage: `0.7243243243243244`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. config SHA-256 与 canonical frozen config 一致 | PASS |
| 2 | 2. status 是 frozen development-only 且 external_access=denied | PASS |
| 3 | 3. 只使用当前 formal release 的 train/validation metadata | PASS |
| 4 | 4. 模型集合和顺序已冻结 | PASS |
| 5 | 5. coverage 与 inconclusive counts 自洽 | PASS |
| 6 | 6. 仅有批准的 aggregate 输出文件 | PASS |
| 7 | 7. 未写样本级 prediction artifact | PASS |
| 8 | 8. consensus runner 未调用 external split loader | PASS |
| 9 | 9. external evaluation 仍未由此 config 授权 | PASS |

本审核只读取 config、development aggregate outputs 与 release 元数据；不读取任何 external split 行。
