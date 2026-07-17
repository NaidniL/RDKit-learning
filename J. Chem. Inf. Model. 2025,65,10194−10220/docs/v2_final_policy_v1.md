# v2 final policy v1

状态：`FROZEN_FINAL_POLICY_PRE_EXTERNAL`。

本政策预注册 v2 final artifact 的训练、三模型共识、指标与 external 隔离规则。它不是 final artifact，也不授权读取新 external；只有后续独立审核和新 external manifest 完成后才可进入评估阶段。

## Frozen decision and AD policy

三成员以固定顺序输出正类（carcinogen）概率，统一阈值为 `0.5`：

```text
all probabilities >= 0.5 -> carcinogen
all probabilities < 0.5  -> noncarcinogen
otherwise                 -> inconclusive
```

AD 采用保守方案：以 final-refit development compounds 的最大 ECFP4 Tanimoto similarity 为描述字段，按 `[0.85,1.00]`、`[0.70,0.85)`、`[0.50,0.70)`、`[0.00,0.50)` 分层报告。AD 不改变 `prediction`，不触发 `inconclusive`。

## Frozen success criteria

- coverage ≥ 0.65；
- covered-set sensitivity、specificity 均 ≥ 0.65；
- v2 covered-set MCC 不低于 v1 在相同 v2 covered subset 上的 MCC；
- inconclusive subset 的平均成员错误率高于 covered subset。

MCC 使用“不低于”而非“严格提高”：在 unanimity covered subset 中，三个成员与共识的 hard call 按定义相同；v2 的预期贡献是选择性拒答和错误拦截，而不是对保留样本重新投票纠错。

完整的机器可读政策、数据与 artifact hashes、成员参数和禁止项见 [v2_final_policy_v1.json](../configs/v2_final_policy_v1.json)。
