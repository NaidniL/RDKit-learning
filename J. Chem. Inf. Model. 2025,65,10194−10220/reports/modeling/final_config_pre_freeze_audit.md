# Final config pre-freeze audit

状态：`AUTOMATED PRE-FREEZE AUDIT PASS — INDEPENDENT AUDIT PENDING`。

审核对象：`configs/final_model_config_v1.json`，其 proposed final config 为 LightGBM +
RDKit/physicochemical descriptors。此审核不访问 external，也不训练 final artifact。

| 检查项 | 结论 | 证据 |
|---|---|---|
| Release pointer / manifest / split hash 一致 | PASS | 所有候选使用 release `20260711_194149_961442_UTC_formal_e20e3008` 和 manifest `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`；各 manifest 记录获准 split hash。 |
| 策略 SHA 一致 | PASS | 策略 SHA 为 `e56583f94f71326fce2d59f63c4027b18445403b27c18eddfc141881cd5cdc10`，与候选报告、冻结配置一致。 |
| 全部预注册树模型候选完成 | PASS | 4 个 RF 与 4 个 LightGBM × ECFP4/MACCS/descriptors/mixed 全部完成。 |
| 每候选一轮 train-tuning CV 网格 | PASS | 每个 manifest 仅有一组 `best_params_from_train_tuning_cv`，使用预注册网格。 |
| 每候选一次 fixed validation | PASS | 每个 manifest 仅记录一次 validation 聚合指标、confusion counts 与 prediction digest。 |
| 无扩网格、改阈值或新增候选 | PASS | 报告和 manifest 的特征/模型集合、`threshold=0.5`、`selection_metric=auroc` 与策略一致。 |
| external 被隔离 | PASS | 8 个树模型 manifest 都是 `external_access=denied`；无 external metric、prediction、digest 或文件。 |
| proposed final 由机械排序得到 | PASS | LightGBM + descriptors validation AUROC=0.765912305516266，为完整候选表唯一最高值。 |
| 缺少 fold-level AUROC std | NOTED / NOT BLOCKING | manifest v1 仅记录 pooled OOF AUROC，无法执行第 4 层 tie-breaker；前两名 AUROC 不完全相同，因此第 1 层已唯一决定排序，不影响本次 proposed final。后续 manifest v2 应记录 fold-level metrics。 |
| Final training strategy 冻结 | PASS | 最终 external 模型固定为 train+validation refit；开发候选仍是 fit train → evaluate validation。 |
| Final threshold strategy 冻结 | PASS | 固定 `threshold=0.5`；不在 validation 或 external 调阈值。 |

## 审计结论

自动化冻结前审核通过。`configs/final_model_config_v1.json` 已冻结为**未 external 评估**的最终配置。

下一道门是独立审核；在其通过前，不得训练最终 artifact，不得更改 frozen config，也不得解锁
`external_final`。
