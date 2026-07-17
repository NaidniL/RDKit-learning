# 基于 RDKit 与机器学习的化学致癌性预测：可审计复刻与 selective consensus 扩展

本项目以 *Toward Explainable Carcinogenicity Prediction: An Integrated Cheminformatics Approach and Consensus Framework*（JCIM, 2025）为方法学起点。它不是对论文数据和实验协议的逐项复现，而是将 RDKit 结构标准化、标签治理、结构泄漏审计、冻结模型工件和一次性 external evaluation 组合成可追溯的毒理机器学习工作流。

## 最终状态

| 版本 | 冻结结论 | 不应作出的表述 |
|---|---|---|
| **v1 单模型基线** | `LightGBM + RDKit/physicochemical descriptors` 已在固定 validation 选择、train+validation refit，并在 CCRIS primary external 上完成一次性评估。 | 不得用 CCRIS external 再调参、调阈值、选模型或重跑。 |
| **v2 selective consensus** | 三成员 unanimity 规则已完成 NTP independent external evaluation，最终为 **`PARTIAL_SUCCESS`**，标签 `final-consensus-v2-external-partial-v1`。 | 不得称为“v2 验证成功”“优于 v1”或“可用于致癌物筛查”。 |

v2 的冻结结果为：49 个 NTP candidate；6 个 carcinogen call、26 个 noncarcinogen call、17 个 inconclusive，coverage `0.653061`。covered subset（n=32）的 MCC/accuracy/sensitivity/specificity 为 `0.647150` / `0.875000` / `0.625000` / `0.958333`。虽然 coverage、同一 covered subset 的 MCC、错误富集和 specificity 达到冻结条件，但 sensitivity `0.625000 < 0.650000`，故 `overall_success=false`。inconclusive 的成员平均错误率为 `0.392157`，高于 covered 的 `0.125000`；同时 carcinogen coverage `0.533333` 低于 noncarcinogen coverage `0.705882`，必须一并解释。

最终发布、机械分类和独立审计位于：

- [最终评估报告](reports/modeling/final_consensus_v2_evaluation_v1/external_evaluation.md)
- [outcome classification](reports/modeling/final_consensus_v2_evaluation_v1/outcome_classification.json)
- [final manifest](reports/modeling/final_consensus_v2_evaluation_v1/evaluation_manifest.json)
- [complete audit（PASS）](reports/modeling/final_consensus_v2_evaluation_v1/complete_audit.md)
- [完整阶段与冻结说明](docs/goal%20v2.md)

最终 v2 release 只读取已经锁定的 aggregate evaluation manifest/report；不重新打开任何 NTP candidate 行。它绑定 source hashes，拒绝重冻结与重写 audit；不保存样本级 prediction CSV。

## 数据与评估边界

- development：CPDB + IRIS，formal release 为 `20260711_194149_961442_UTC_formal_e20e3008`，train/validation/final-refit 分别为 736/185/921。
- v1 primary external：CCRIS，不能作为 v2 final external。
- v2 external：NTP/NICEATM Cancer Bioassay Chemicals 的保守二分类候选；相对 development 的 exact、connectivity 和 tautomer overlap 均为零。
- v2 输出固定：所有成员概率 `>=0.5` 为 `carcinogen`；全部 `<0.5` 为 `noncarcinogen`；否则为 `inconclusive`，必须人工复核。AD 仅作描述，不能改变 call。
- 模型、特征、阈值和 policy 在 external 结果出现后没有改动。

## 安装与自检

已验证环境：Python 3.10.20、RDKit 2023.9.6、LightGBM 4.5.0、scikit-learn 1.5.1。macOS 上 LightGBM 需要 OpenMP：

```bash
brew install python@3.10 libomp
cd "J. Chem. Inf. Model. 2025,65,10194−10220"
make setup
source .venv/bin/activate
make check
make test
```

`requirements-lock.txt` 是当前验证环境的完整依赖快照；`requirements.txt` 是运行时直接依赖，`requirements-dev.txt` 增加研发工具。

## 可复现与审计入口

| 入口 | 用途与边界 |
|---|---|
| `scripts/assemble_modeling_dataset.py` | 审计并生成 formal dataset release；训练只通过 release manifest 读取数据。 |
| `scripts/train_model.py` | v1 候选训练、final refit 与其受控 external-final 流程。 |
| `scripts/train_v2_final_artifact.py --no-external` | 只用 train+validation 重训 v2 三成员 final artifact。 |
| `scripts/audit_v2_final_policy.py` / `audit_v2_final_artifact.py` | 审核 v2 policy 和 final artifact。 |
| `scripts/audit_v2_external_evaluation.py --require-complete` | 审核已完成的一次性 NTP external evaluation，不读取 external 行。 |
| `scripts/audit_v2_final_outcome.py` | 最终 release 的初始 complete audit；release 完成后拒绝改写。 |

常规验证可运行：

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_selective_prediction.py \
  tests/test_v2_final_policy.py \
  tests/test_v2_final_artifact.py \
  tests/test_v2_external_ntp_candidate.py \
  tests/test_v2_external_evaluation_audit.py \
  tests/test_v2_final_outcome.py
```

## 项目结构

```text
configs/     # 冻结 policy、输出契约和 one-shot authorization
data/        # 原始、中间和处理数据（默认不提交）
docs/        # 数据/训练策略、v2 阶段目标与冻结边界
models/      # v1/v2 final-refit 模型工件
releases/    # 版本化 formal dataset release 与 manifest
reports/     # 清洗、建模、external、最终结论与审计报告
scripts/     # 可复现命令行入口与独立审核
src/         # 标准化、特征、模型、指标和 guard
tests/       # 自动化验证
```

本项目仅用于研究性方法开发和辅助筛查；二元标签压缩了剂量、物种、暴露途径和证据等级，不能直接用于临床、监管审批或个体安全决策。
