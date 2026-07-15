# v1 diagnostic scope addendum

本 addendum 记录后来明确授权的唯一例外：在最终 primary external evaluation 已锁定且完成后，进行一次仅描述性的 post-hoc external error、similarity/scaffold stratification 与 domain-aware performance 诊断。

该例外由 `configs/v1_posthoc_external_diagnostic_authorization_v1.json` 固定，并且：

- 只读取已冻结的 v1 model、preprocessing、formal release 和 primary external；
- 不改变模型、特征、预处理、threshold（仍为 0.5）或模型选择；
- 不写样本级 external prediction 文件，只保留 canonical prediction digest；
- 输出目录一旦存在即拒绝重复运行；
- 任何观察到的误差模式、相似度/骨架分层或 domain 指标均不得回流为 v1 的开发或调参反馈。

因此，先前 `v1_diagnostic_scope_audit.md` 中的“external error analysis 不在原始锁定范围内”仍是历史事实；本文件及独立 audit 仅记录本次显式、一次性、描述性授权。
