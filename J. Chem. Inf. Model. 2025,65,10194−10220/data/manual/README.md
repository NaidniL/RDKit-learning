# 人工审核决策

`inorganic_carbon_decisions.csv` 用于将疑似无机含碳结构的人工审核结果可复现地输入数据清洗流程。

| 字段 | 要求 |
|---|---|
| `standard_inchikey` | 必须来自当前 `inorganic_carbon_review.csv` |
| `decision` | 只能是 `include` 或 `exclude` |
| `review_reason` | 必填，记录审核依据 |
| `reviewer` | 必填，记录审核人 |

`include` 会将结构纳入可建模数据；`exclude` 会保留人工排除原因。未填写决策的疑似结构继续保留在审核集，
不进入模型数据。未知 InChIKey、重复决策、非法决策或缺少审核信息会直接报错。

推荐流程：先执行一次 `--dry-run`，从
`reports/cleaning/audits/<run-id>/inorganic_carbon_review.csv` 取得待审核 InChIKey；填写本决策表后，
必须重新执行 `--dry-run` 并审核新批次。正式运行只能引用最终审核通过的新 `run-id`。

## 建模标签冲突的固定裁决规则

阶段 2 的来源标签冲突不使用 `modeling_conflict_decisions.csv` 进行人工改标，而由组装程序使用固定计数
规则确定性处理。对每个 `compound_id,dataset_role`，只比较 `clear_positive_count` 与
`clear_negative_count`：

1. 两者之和小于或等于 10，排除；
2. 否则，两者差值的绝对值小于或等于 10，排除；
3. 否则，记录数更多的一方为最终标签：阳性更多标记为 `positive`（二分类标签 `1`），阴性更多标记为
   `negative`（二分类标签 `0`）。

该规则按顺序执行，且结果由 `modeling/conflict_reviews.csv` 与
`reports/modeling_conflict_review_candidates.csv` 完整记录。不得创建或手工编辑
`data/manual/modeling_conflict_decisions.csv`，否则它不会改变模型数据，也不构成有效审核输入。
