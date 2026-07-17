**v2 已完成独立 external 验证，但按预注册标准应判定为“部分成功”，不能判定为“完全成功”。**

这个结论很干净，而且比事后放宽 sensitivity 门槛更有价值。

从结果看，v2 的核心研究假设得到了相当强的支持：

- coverage 为 65.31%，刚刚达到一个可用但偏低的水平；
    
- covered subset 上 MCC 0.647、accuracy 0.875，说明在模型愿意一致作答时，预测质量较高；
    
- specificity 0.958，说明覆盖范围内假阳性控制得很好；
    
- inconclusive 样本的成员平均错误率为 0.392，明显高于 covered 样本的 0.125，说明模型分歧确实成功富集了困难样本；
    
- 独立 NTP external 未参与 v2 设计，且 exact、connectivity、tautomer 三层重叠均为零；
    
- one-shot lock、无样本级预测、禁止重跑、模型与 policy 不变，保证了结果的确认性。
    

但 sensitivity 为 0.625，低于预注册下限 0.65，因此不能声称 v2 达到了完整的筛查目标。这里即使只差 0.025，也不能事后说“差不多算通过”。49 个样本本身较少，covered positive 数更少，少预测对一个阳性样本就可能让 sensitivity 从 0.625 上升到 0.75；这说明点估计波动可能很大，但在没有预注册置信区间判定规则的情况下，仍应机械地按失败处理。


建议将 v2 的最终状态写为：

> **v2 selective consensus system：独立 external 验证部分成功。**  
> 该系统在预注册 coverage 范围内表现出较高的 covered-set MCC、accuracy 和 specificity，且 inconclusive 输出有效富集了成员模型的错误。然而，covered-set sensitivity 为 0.625，低于预注册最低要求 0.65，因此未满足“完全成功”的全部判据。

不要使用：

- “v2 验证成功”；
    
- “v2 优于 v1”；
    
- “v2 已可用于致癌物筛查”；
    
- “共识模型显著提高性能”。
    

更准确的标题可以是：

> **Independent external validation of a selective carcinogenicity consensus: strong specificity and error interception, but insufficient sensitivity**

## 现在应立即完成的收尾

### 1. 冻结结果判定文件

建立类似：

```text
reports/modeling/final_consensus_v2_evaluation_v1/
├── external_evaluation.md
├── outcome_classification.json
├── evaluation_manifest.json
└── complete_audit.md
```

`outcome_classification.json` 应机械记录：

```json
{
  "status": "PARTIAL_SUCCESS",
  "coverage_pass": true,
  "covered_mcc_pass": true,
  "error_enrichment_pass": true,
  "sensitivity_pass": false,
  "overall_success": false,
  "failure_reason": "covered sensitivity 0.625000 < preregistered minimum 0.650000"
}
```

不要只在 Markdown 中人工解释，避免以后被重新诠释。

### 2. 打最终标签

建议标签名称明确包含“partial”或“evaluated”，例如：

```text
final-consensus-v2-external-partial-v1
```

或：

```text
consensus-v2-external-evaluated-v1
```

不建议使用：

```text
final-model-v2-success
consensus-v2-validated
```

因为它们会掩盖 sensitivity 未达标。

### 3. 补充不确定性区间，但不得改变判定

现在可以进行**纯描述性的统计区间分析**，前提是：

- 不重新读取 external 行；
    
- 只使用已锁定的聚合 confusion matrix；
    
- 不改变 PASS/FAIL；
    
- 不据此修改 policy。
    

covered subset 的 sensitivity 0.625 很可能对应 5/8 个阳性预测正确；specificity 0.9583 很可能对应 23/24 个阴性判断正确。若确实如此，样本量非常小，应报告 Wilson 或 Clopper–Pearson 区间，突出估计不稳定性。

但无论区间是否跨过 0.65，冻结判定仍然是：

> sensitivity criterion failed.

置信区间只能帮助解释结果，不能代替预注册点估计门槛。

### 4. 与成员模型做冻结好的公平比较

确认 external 报告已经包括：

- 三个成员在全部 49 个样本上的表现；
    
- 三个成员在相同 32 个 covered subset 上的表现；
    
- consensus 与成员在同一 covered subset 的差异；
    
- 17 个 inconclusive 中各成员错误情况；
    
- carcinogen 与 noncarcinogen 的 class-conditional coverage。
    

这里尤其要看：

> v2 是否主要通过拒答阳性样本换来了高 specificity。

总数据中阳性为 15、阴性为 34，而 covered sensitivity 只有 0.625。如果阳性 coverage 明显低于阴性 coverage，v2 的实际行为可能是更倾向于拒答或漏掉致癌物。这个结果必须显式报告，不能只突出总体 coverage 0.653。

### v2 最终冻结完成

- 最终发布目录为 [`final_consensus_v2_evaluation_v1`](../reports/modeling/final_consensus_v2_evaluation_v1/)，标签固定为 `final-consensus-v2-external-partial-v1`。它只绑定既有的 external aggregate manifest/report，不重新读取任何 NTP candidate 行。
- [`outcome_classification.json`](../reports/modeling/final_consensus_v2_evaluation_v1/outcome_classification.json) 已机械锁定为 `PARTIAL_SUCCESS`：coverage、同 covered subset MCC、错误富集和 specificity 通过；sensitivity 不通过，`overall_success=false`。
- Wilson 95% 区间仅作描述：sensitivity 5/8 为 `[0.305742, 0.863156]`，specificity 23/24 为 `[0.797582, 0.992607]`；不改变预注册点估计判定。
- 最终报告补充了 17 个 inconclusive 中三成员的聚合错误数（9、5、6），并保留 class-conditional coverage 的不平衡：carcinogen `0.533333`，noncarcinogen `0.705882`。
- [`complete_audit.md`](../reports/modeling/final_consensus_v2_evaluation_v1/complete_audit.md) 为 `PASS`，验证来源 hashes、机械分类、描述性区间和不夸大 final tag。该目录及其审计均拒绝重冻结/改写。
