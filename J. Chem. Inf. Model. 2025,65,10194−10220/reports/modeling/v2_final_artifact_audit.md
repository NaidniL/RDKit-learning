# v2 final-artifact audit

状态：`PASS`。

## Immutable metadata

- artifact_dir: `/Users/lydia/本地文件/RDkit/J. Chem. Inf. Model. 2025,65,10194−10220/models/final_consensus_v2`
- v2_final_policy_sha256: `be320418ce7852ec48ff386dccfa79e9752e914392bfafa8b331cdda14045826`
- dataset_release_id: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset_manifest_sha256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`

## Checks

| # | Check | Status |
|---:|---|---|
| 1 | 1. v2 final artifact 目录存在 | PASS |
| 2 | 2. artifact 文件集合严格匹配 | PASS |
| 3 | 3. artifact 内 policy 与冻结 policy byte-identical | PASS |
| 4 | 4. policy、training、consensus 和 environment manifest hashes 对齐 | PASS |
| 5 | 5. formal release identity 与 train/validation artifact hashes 对齐 | PASS |
| 6 | 6. 三成员均在 train+validation 921 样本上重训 | PASS |
| 7 | 7. feature manifest 与三个冻结 feature sets 对齐 | PASS |
| 8 | 8. 三成员参数、模型及 preprocessing artifacts 可复核 | PASS |
| 9 | 9. consensus rule、output contract 和保守 AD policy 对齐 | PASS |
| 10 | 10. 非自引用 artifact hashes 完整匹配 | PASS |
| 11 | 11. 不含 predictions/metrics，所有 manifest external_access=denied | PASS |

本审核只读取 final artifacts、policy 与 formal release metadata；不读取任何 split 行或 external 数据。
