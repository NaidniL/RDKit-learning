# v1 post-hoc domain-aware performance

状态：`COMPLETE — DESCRIPTIVE ONLY`。

固定的 post-hoc domain categories：in-domain = maximum ECFP4 similarity >= 0.70 且 Murcko scaffold 在 train 中出现；near-domain = similarity >= 0.50 但不满足 in-domain；out-of-domain = similarity < 0.50。类别仅用于描述已冻结结果，不改变其 0.5 threshold 或 coverage。

| Domain | Samples | Mean similarity | Train-seen scaffold | AUROC | MCC | Accuracy | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---:|---:|---|
| in_domain | 11 | 0.790641 | 11 | 1.000000 | 1.000000 | 1.000000 | 4 / 0 / 0 / 7 |
| near_domain | 125 | 0.609824 | 45 | 0.799141 | 0.362531 | 0.704000 | 26 / 23 / 14 / 62 |
| out_of_domain | 319 | 0.326778 | 86 | 0.667393 | 0.229184 | 0.608150 | 100 / 46 / 79 / 94 |

此 domain 分层是 post-hoc 描述，不是经过外测优化的部署拒答规则。任何未来规则必须在 development 数据上预注册。
