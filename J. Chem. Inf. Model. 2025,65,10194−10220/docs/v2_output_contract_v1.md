# v2 output contract v1

状态：`FROZEN_OUTPUT_CONTRACT_NOT_FINAL_MODEL_POLICY`。

v2 是一个选择性致癌性筛查系统，而不是一个要求对每个化合物强制给出二分类的“更高分模型”。它联合三个固定成员的致癌概率；只有所有成员同向时才给出二分类，否则拒答并要求复核。

本契约绑定 [v2_output_contract_v1.json](../configs/v2_output_contract_v1.json) 和开发期配置 `consensus_v2_development_v1.json` 的 SHA-256 `d6beda993b141750e254cd869e8451a444e92e14d9fb97f24b3d80cd865485f3`。

## Fixed decision rule

成员顺序固定为：`lightgbm_descriptors`、`random_forest_maccs`、`random_forest_ecfp4`。各成员输出的是“致癌（positive）”的概率，统一阈值为 `0.5`；等于 `0.5` 归为 positive。

| 条件 | `prediction` | `decision_reason` | `review_required` |
|---|---|---|---:|
| 全部三个概率 `>= 0.5` | `carcinogen` | `unanimous_carcinogen` | false |
| 全部三个概率 `< 0.5` | `noncarcinogen` | `unanimous_noncarcinogen` | false |
| 其余全部情形（成员 hard call 不一致） | `inconclusive` | `member_disagreement` | true |

`inconclusive` 是受控的拒答输出（中文可显示为“未知／需复核”），不是负类、不是预测错误，也不是模型宣称“不存在致癌风险”。它要求人工复核或补充证据后才能形成业务结论。

## Stable output shape

每个输入样本必须得到且只得到下列四个字段；外层应用可附加样本标识，但不得改变这四个字段的含义或枚举值。

```json
{"schema_version":"v2_output_contract_v1","prediction":"inconclusive","decision_reason":"member_disagreement","review_required":true}
```

`prediction` 的闭集仅为：`carcinogen`、`noncarcinogen`、`inconclusive`。v2 没有连续“consensus probability”，因此不得把任意成员概率或均值冒充为系统概率。

## Boundaries of this freeze

- 当前唯一的拒答触发条件是成员分歧。适用域、相似度、校准、投票加权和动态阈值均不改变 `prediction`。
- 此文件冻结输出语义和决策规则；它不替代后续 v2 final policy、三成员 final-refit artifact 或新的独立 external 评估授权。
- `external_access` 在本契约中未获授权，v1 primary external 不能用于改变该规则。
