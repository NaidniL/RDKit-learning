# Final model v1 summary

状态：`FROZEN AND ARCHIVED`。

本报告只汇总已冻结的 v1 artifact、审核记录和一次性 primary external evaluation；不引入新的模型选择、阈值选择、特征修改或 external 分析。

## Data release

- Dataset release：`20260711_194149_961442_UTC_formal_e20e3008`
- Dataset manifest SHA-256：`b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- Development fixed splits：train `736`、validation `185`。
- Final refit：train+validation，共 `921` 个样本（class 0=`503`，class 1=`418`）。
- Primary external：`455` 个样本；split SHA-256 为 `5070aa855385795106e4c45c3f74dc6616ba11d912ec017d729f2ec09dc12714`。

## Training strategy

- 所有候选都使用固定 train-tuning CV 做调参，并只在 fixed validation 上评估一次。
- 预注册选择规则的主指标是 validation AUROC；最终选择已在 external 读取前冻结。
- 最终模型使用已冻结配置在 train+validation 上 refit；descriptor median imputation 在该 refit 数据上拟合。
- primary external evaluation 只执行一次，固定 threshold=`0.5`，没有写出样本级 prediction 文件，仅记录 canonical prediction digest。

## Candidate models

候选批次包含 RandomForest 和 LightGBM 两个模型族，分别搭配 ECFP4、MACCS、descriptors 与 mixed 四种特征集，共 `8` 个预注册树模型候选。按 validation AUROC 的机械排序，排名第一的是 LightGBM + descriptors。

## Final model

- Model：LightGBM + RDKit/physicochemical descriptors。
- Input descriptors：`220` 列；median imputation 后移除 `11` 个常数列，保留 `209` 列。
- Frozen parameters：`num_leaves=31`、`learning_rate=0.03`、`n_estimators=300`、`min_child_samples=10`、`reg_lambda=0`。
- Runtime controls：`random_state=42`、`n_jobs=1`、`deterministic=true`。
- Threshold：`0.5`。

## Validation result

| Metric | Value |
|---|---:|
| AUROC | 0.765912 |
| AUPRC | 0.7896 |
| MCC | 0.3806 |
| Sensitivity | 0.6786 |
| Specificity | 0.7030 |
| Confusion (TN / FP / FN / TP) | 71 / 30 / 27 / 57 |

## Primary external result

| Metric | Value |
|---|---:|
| Samples | 455 |
| AUROC | 0.719437 |
| AUPRC | 0.772798 |
| Accuracy | 0.643956 |
| Balanced accuracy | 0.644993 |
| MCC | 0.287757 |
| Sensitivity | 0.636719 |
| Specificity | 0.653266 |
| Confusion (TN / FP / FN / TP) | 130 / 69 / 93 / 163 |

Validation AUROC 与 primary external AUROC 的差为 `0.046475`。

## Limitations and v1 lock

- primary external 是一次性最终评估；其结果不得回流到模型选择、调参、特征修改或 threshold 修改。
- v1 不包含 external prediction CSV；只保存 prediction digest。
- 本报告不包含 tautomer-clean sensitivity external 的结果。
- `final-model-external-v1` 标签及其关联 manifest、artifact 和审核报告共同构成 v1 封存记录。
