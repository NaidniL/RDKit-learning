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
