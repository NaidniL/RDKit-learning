# v2 development-only selective-prediction diagnostics

状态：`POST HOC, DEVELOPMENT ONLY`。

本报告使用冻结的三成员 v2 config，在同一 train fit / fixed validation 过程上重现聚合统计。它不读取 external、不写样本级预测、不改变成员、参数、阈值或 unanimity 规则。下面所有风险覆盖策略均为 exploratory 诊断，不能据此事后选择 v2 final rule。

## Locked inputs

- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- train / validation: `736 / 185`
- threshold: `0.5`
- external access: `denied`

## 1. Fair comparison on the same unanimity-covered subset

unanimity 覆盖 134/185 个 validation 样本（coverage=0.724324）。consensus 的概率列是 hard call（0/1），因此未定义 AUROC/AUPRC；三个成员的 AUROC/AUPRC 则使用它们各自在同一 134 个样本上的连续概率。

| Model | Evaluation population | n samples | Coverage of validation | AUROC | AUPRC | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| unanimity_consensus | unanimity_covered | 134 | 0.724324 | not_defined | not_defined | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |
| lightgbm_descriptors | same_unanimity_covered | 134 | 0.724324 | 0.811148 | 0.844939 | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |
| random_forest_maccs | same_unanimity_covered | 134 | 0.724324 | 0.777146 | 0.807667 | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |
| random_forest_ecfp4 | same_unanimity_covered | 134 | 0.724324 | 0.759532 | 0.789231 | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |

在 unanimity-covered subset 内，三个成员的 hard call 按定义完全一致，因此它们与 consensus 的 MCC、accuracy、sensitivity、specificity 和混淆计数完全相同。该规则在这里的作用是选择性拒答，不是通过投票修正 covered 样本的成员分类错误。

## 2. Error enrichment in inconclusive samples

错误率以固定 0.5 hard call 计算。Fisher exact test 为两侧、未作多重比较校正的探索性检验；它描述当前 validation 的关联，不能作为 final-policy 选择依据。

`any_member_wrong` 在 inconclusive 中必为 1，而 `all_members_wrong` 在 inconclusive 中必为 0：这是二元真值与硬预测不一致的逻辑结果，而非独立的错误富集发现。其行按计划完整保留，但应主要解读各成员错误率与 `≥2 members wrong`。

| Subset | n | LightGBM-descriptors error | RF-MACCS error | RF-ECFP4 error | Any member wrong | ≥2 members wrong | All 3 members wrong |
|---|---:|---:|---:|---:|---:|---:|---:|
| covered | 134 | 0.238806 | 0.238806 | 0.238806 | 0.238806 | 0.238806 | 0.238806 |
| inconclusive | 51 | 0.490196 | 0.470588 | 0.470588 | 1.000000 | 0.431373 | 0.000000 |

| Error event | Covered error count/rate | Inconclusive error count/rate | Fisher odds ratio (inconclusive vs covered) | Two-sided p value |
|---|---|---|---:|---:|
| lightgbm_descriptors wrong | 32 / 134 (0.238806) | 25 / 51 (0.490196) | 3.064904 | 0.001331 |
| random_forest_maccs wrong | 32 / 134 (0.238806) | 24 / 51 (0.470588) | 2.833333 | 0.003820 |
| random_forest_ecfp4 wrong | 32 / 134 (0.238806) | 24 / 51 (0.470588) | 2.833333 | 0.003820 |
| any_member_wrong | 32 / 134 (0.238806) | 51 / 51 (1.000000) | inf | 0.000000 |
| at_least_two_members_wrong | 32 / 134 (0.238806) | 22 / 51 (0.431373) | 2.418103 | 0.011975 |
| all_members_wrong | 32 / 134 (0.238806) | 0 / 51 (0.000000) | 0.000000 | 0.000015 |

## 3. Exploratory risk-coverage curves

每个策略不使用标签排序：`mean_margin` 为三个概率到 0.5 的平均距离；`minimum_margin` 为最小距离；`hard_vote_agreement_then_mean_margin` 先按 hard-call 多数票一致度（3/3 优于 2/3），再按平均距离。目标 coverage 以 `ceil(target × 185)` 取样；分数并列时按验证集冻结行顺序打破，不输出样本身份。risk = 1 − accuracy。

| Strategy | Target coverage | Actual n / coverage | Risk | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |
|---|---:|---|---:|---:|---:|---:|---:|---|
| mean_margin | 1.000000 | 185 / 1.000000 | 0.270270 | 0.452203 | 0.729730 | 0.654762 | 0.792079 | 80 / 21 / 29 / 55 |
| mean_margin | 0.950000 | 176 / 0.951351 | 0.272727 | 0.449033 | 0.727273 | 0.641975 | 0.800000 | 76 / 19 / 29 / 52 |
| mean_margin | 0.900000 | 167 / 0.902703 | 0.269461 | 0.454082 | 0.730539 | 0.644737 | 0.802198 | 73 / 18 / 27 / 49 |
| mean_margin | 0.800000 | 148 / 0.800000 | 0.263514 | 0.479112 | 0.736486 | 0.643836 | 0.826667 | 62 / 13 / 26 / 47 |
| mean_margin | 0.724324 | 134 / 0.724324 | 0.231343 | 0.548923 | 0.768657 | 0.676471 | 0.863636 | 57 / 9 / 22 / 46 |
| mean_margin | 0.600000 | 111 / 0.600000 | 0.252252 | 0.506741 | 0.747748 | 0.672414 | 0.830189 | 44 / 9 / 19 / 39 |
| mean_margin | 0.500000 | 93 / 0.502703 | 0.258065 | 0.494875 | 0.741935 | 0.686275 | 0.809524 | 34 / 8 / 16 / 35 |
| minimum_margin | 1.000000 | 185 / 1.000000 | 0.270270 | 0.452203 | 0.729730 | 0.654762 | 0.792079 | 80 / 21 / 29 / 55 |
| minimum_margin | 0.950000 | 176 / 0.951351 | 0.278409 | 0.437372 | 0.721591 | 0.641975 | 0.789474 | 75 / 20 / 29 / 52 |
| minimum_margin | 0.900000 | 167 / 0.902703 | 0.281437 | 0.435309 | 0.718563 | 0.632911 | 0.795455 | 70 / 18 / 29 / 50 |
| minimum_margin | 0.800000 | 148 / 0.800000 | 0.270270 | 0.466445 | 0.729730 | 0.630137 | 0.826667 | 62 / 13 / 27 / 46 |
| minimum_margin | 0.724324 | 134 / 0.724324 | 0.261194 | 0.486864 | 0.738806 | 0.641791 | 0.835821 | 56 / 11 / 24 / 43 |
| minimum_margin | 0.600000 | 111 / 0.600000 | 0.297297 | 0.418593 | 0.702703 | 0.627119 | 0.788462 | 41 / 11 / 22 / 37 |
| minimum_margin | 0.500000 | 93 / 0.502703 | 0.268817 | 0.476190 | 0.731183 | 0.666667 | 0.809524 | 34 / 8 / 17 / 34 |
| hard_vote_agreement_then_mean_margin | 1.000000 | 185 / 1.000000 | 0.270270 | 0.452203 | 0.729730 | 0.654762 | 0.792079 | 80 / 21 / 29 / 55 |
| hard_vote_agreement_then_mean_margin | 0.950000 | 176 / 0.951351 | 0.278409 | 0.435595 | 0.721591 | 0.637500 | 0.791667 | 76 / 20 / 29 / 51 |
| hard_vote_agreement_then_mean_margin | 0.900000 | 167 / 0.902703 | 0.269461 | 0.455911 | 0.730539 | 0.649351 | 0.800000 | 72 / 18 / 27 / 50 |
| hard_vote_agreement_then_mean_margin | 0.800000 | 148 / 0.800000 | 0.236486 | 0.531254 | 0.763514 | 0.661972 | 0.857143 | 66 / 11 / 24 / 47 |
| hard_vote_agreement_then_mean_margin | 0.724324 | 134 / 0.724324 | 0.238806 | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |
| hard_vote_agreement_then_mean_margin | 0.600000 | 111 / 0.600000 | 0.252252 | 0.506741 | 0.747748 | 0.672414 | 0.830189 | 44 / 9 / 19 / 39 |
| hard_vote_agreement_then_mean_margin | 0.500000 | 93 / 0.502703 | 0.258065 | 0.494875 | 0.741935 | 0.680000 | 0.813953 | 35 / 8 / 16 / 34 |

### Fixed unanimity point

| Rule | n / coverage | Risk | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |
|---|---|---:|---:|---:|---:|---:|---|
| fixed_unanimity | 134 / 0.724324 | 0.238806 | 0.525774 | 0.761194 | 0.676923 | 0.840580 | 58 / 11 / 21 / 44 |

## Interpretation boundary

- 同一 covered subset 的比较才可用于判断 unanimity hard call 与成员 hard call 的相对表现；它不能替代独立 external 证据。
- 当前 covered subset 中成员与 consensus 的 hard-call 表现相同，因此 development 证据支持的定位是“选择性拒答层”，而不是“已证明提升 covered 样本分类性能的集成器”。
- risk-coverage 曲线用于判断固定 unanimity 点是否位于合理区域，不授权根据曲线事后挑选更好看的阈值或规则。
- 任何 v2 final policy 必须在新的 external 访问前另行预注册、冻结并独立审核；v1 primary external 始终不得用于 v2 选择。
