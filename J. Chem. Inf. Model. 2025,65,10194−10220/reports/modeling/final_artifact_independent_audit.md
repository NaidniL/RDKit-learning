# Final artifact independent audit

状态：`PASS`。

## Immutable metadata

- artifact_dir: `/Users/lydia/本地文件/RDkit/J. Chem. Inf. Model. 2025,65,10194−10220/models/final_model_v1`
- final_model_config_sha256: `19a0ca3d720c940e6574b43abfee13a6f7ca76f73d67b13ef60b7844fef6f486`
- dataset_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset_manifest_sha256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- model_artifact_sha256: `03d0b9bb6c8314200f75c1f57c914b0b7b81cbca410af4913fadfb2046bdd47c`
- preprocessing_artifact_sha256: `3a01178098e0b62a117f84cf4867745378b153d4ddde911ff023d6f342aa5d57`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. final artifact 目录存在 | PASS |
| 2 | 2. 仅存在批准的五个 artifact | PASS |
| 3 | 3. training manifest schema/version 固定 | PASS |
| 4 | 4. final config SHA-256 与冻结配置相符 | PASS |
| 5 | 5. frozen config 仍为 LightGBM + descriptors | PASS |
| 6 | 6. fit split 是 train+validation | PASS |
| 7 | 7. refit 样本数和类别计数完整 | PASS |
| 8 | 8. release ID、manifest 及 train/validation hashes 相符 | PASS |
| 9 | 9. feature set 是 220 个 descriptors | PASS |
| 10 | 10. feature manifest SHA-256 相符 | PASS |
| 11 | 11. median 在 train+validation 拟合且常数列移除可复核 | PASS |
| 12 | 12. LightGBM params、random_state、n_jobs、deterministic 一致 | PASS |
| 13 | 13. threshold 固定为 0.5 | PASS |
| 14 | 14. model artifact SHA-256 和 bytes 相符 | PASS |
| 15 | 15. preprocessing artifact SHA-256 和 bytes 相符 | PASS |
| 16 | 16. code revision 与 runtime signature 已记录 | PASS |
| 17 | 17. external access 明确 denied | PASS |
| 18 | 18. 不含预测、指标或未批准 artifact | PASS |

本审核只读取 final artifacts、冻结 config、release pointer/manifest 元数据；不读取任何 split 行或 external 数据。
