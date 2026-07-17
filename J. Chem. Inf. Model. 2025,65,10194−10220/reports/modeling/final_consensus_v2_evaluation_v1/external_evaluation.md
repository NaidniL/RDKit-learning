# v2 one-shot NTP external evaluation

状态：`COMPLETE`。

此报告是用户授权的唯一一次 NTP candidate external evaluation。未读取 v1 CCRIS external；没有改变 policy、成员、预处理、阈值或 AD call。仅保留聚合统计和 prediction digest，不写样本级 prediction artifact。

## Calls and coverage

| Total | Carcinogen calls | Noncarcinogen calls | Inconclusive | Coverage | Carcinogen coverage | Noncarcinogen coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 49 | 6 | 26 | 17 | 0.653061 | 0.533333 | 0.705882 |

## Same-covered-subset comparison

| Model | Population | n | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |
|---|---|---:|---:|---:|---:|---:|---|
| v2 consensus | v2 covered subset | 32 | 0.647150 | 0.875000 | 0.625000 | 0.958333 | 23 / 1 / 3 / 5 |
| lightgbm_descriptors | v2 covered subset | 32 | 0.647150 | 0.875000 | 0.625000 | 0.958333 | 23 / 1 / 3 / 5 |
| random_forest_maccs | v2 covered subset | 32 | 0.647150 | 0.875000 | 0.625000 | 0.958333 | 23 / 1 / 3 / 5 |
| random_forest_ecfp4 | v2 covered subset | 32 | 0.647150 | 0.875000 | 0.625000 | 0.958333 | 23 / 1 / 3 / 5 |

## Member full-external performance

| Member | n | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |
|---|---:|---:|---:|---:|---:|---|
| lightgbm_descriptors | 49 | 0.387341 | 0.734694 | 0.600000 | 0.794118 | 27 / 7 / 6 / 9 |
| random_forest_maccs | 49 | 0.560112 | 0.816327 | 0.666667 | 0.882353 | 30 / 4 / 5 / 10 |
| random_forest_ecfp4 | 49 | 0.519608 | 0.795918 | 0.666667 | 0.852941 | 29 / 5 / 5 / 10 |

## Error interception

- mean member error rate, covered / inconclusive: `0.125000` / `0.392157`
- member error events in rejected subset: `20` of `32` (`0.625000`)
- any-member-wrong rate, covered / inconclusive: `0.125000` / `1.000000`

## AD and scaffold strata

| Stratum | n | Covered | Coverage | Covered MCC |
|---|---:|---:|---:|---:|
| AD similarity [0.85,1.00] | 0 | 0 | null | null |
| AD similarity [0.70,0.85) | 3 | 2 | 0.666667 | 0.000000 |
| AD similarity [0.50,0.70) | 13 | 7 | 0.538462 | 1.000000 |
| AD similarity [0.00,0.50) | 33 | 23 | 0.696970 | 0.647098 |
| Scaffold seen in final-refit development | 30 | 17 | 0.566667 | 0.717137 |
| Scaffold novel to final-refit development | 19 | 15 | 0.789474 | 0.583333 |

## Frozen success-criterion readout

- coverage ≥ 0.65: `True`
- covered sensitivity / specificity ≥ 0.65: `False` / `True`
- inconclusive mean member error rate > covered: `True`
- v2 MCC ≥ v1 MCC on same v2 covered subset: `True` (v2 `0.647150`, v1 `0.647150`)

Tautomer diagnostic：所有 candidate 在 candidate-construction overlap audit 中均与 development tautomer family 零重叠；本次仅描述该边界，不改变输入结构或 call。

## Frozen final outcome

- Final status: `PARTIAL_SUCCESS`。
- 预注册判定不因区间而改变：coverage、同 covered subset MCC、错误富集和 specificity 通过；covered sensitivity 不通过（`0.625000 < 0.650000`）。
- Covered sensitivity Wilson 95% CI (5/8): `[0.305742, 0.863156]`；covered specificity Wilson 95% CI (23/24): `[0.797582, 0.992607]`。区间仅描述小样本不稳定性，不能替代已冻结点估计门槛。
- 因此不得称为‘验证成功’、‘优于 v1’或‘可用于致癌物筛查’；准确表述是：独立 external 验证部分成功。

## Inconclusive-member aggregate errors

| Member | Full errors | Covered errors | Inconclusive errors |
|---|---:|---:|---:|
| lightgbm_descriptors | 13 | 4 | 9 |
| random_forest_ecfp4 | 10 | 4 | 6 |
| random_forest_maccs | 9 | 4 | 5 |
