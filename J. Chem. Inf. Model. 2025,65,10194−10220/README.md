# 基于 RDKit 与机器学习的化学致癌性预测模型复刻与扩展

本目录用于复刻 *Toward Explainable Carcinogenicity Prediction: An Integrated Cheminformatics Approach and Consensus Framework* 的主要流程，并扩展 Morgan 指纹、PR-AUC 评估及可复用的 Streamlit 预测原型。

## 环境基线

- macOS Apple Silicon（当前已验证环境）
- Python 3.10.20
- RDKit 2023.9.6（论文报告版本）
- TensorFlow 2.17.0 + Keras 3.4.1（论文报告版本）
- Streamlit 1.46.0（论文报告版本）
- LightGBM 4.5.0、scikit-learn 1.5.1、SHAP 0.46.0（论文未报告版本，本项目固定版本）

LightGBM 在 macOS 上需要 OpenMP：

```bash
brew install python@3.10 libomp
```

## 安装与自检

```bash
cd "J. Chem. Inf. Model. 2025,65,10194−10220"
make setup
source .venv/bin/activate
```

重复自检：

```bash
make check
```

自检会验证 RDKit 分子解析、MACCS/Morgan/E-state/分子描述符生成，以及 LightGBM、Random Forest 和最小 BiLSTM 前向计算。

`requirements.txt` 是 Streamlit/运行时的直接依赖，`requirements-dev.txt` 增加研发工具，`requirements-lock.txt` 则保存当前已验证环境的完整依赖快照，`make setup` 默认按该快照安装。

## 论文复刻参数基线

- ECFP/Morgan：radius=10，4096 bits（复刻）；radius=2，2048 bits（扩展基线）
- MACCS：167 keys
- RDKit path fingerprint：2048 bits
- E-state：79 维
- BiLSTM：64/32 隐藏单元，每层 dropout=0.3，Dense(100, ReLU)，Adam lr=0.001，20 epochs，batch size=32
- RF：100 trees，random_state=42
- LightGBM：100 estimators，random_state=42
- 数据切分：分层 80:20，并执行 stratified 5-fold CV
- 评估：Accuracy、ROC-AUC、PR-AUC（扩展）、MCC、Sensitivity、Specificity
- 共识规则：三个模型概率均 >= 0.5 为致癌，均 < 0.5 为非致癌，否则为不确定

## 预定项目结构

```text
data/                 # 原始、中间及处理后数据（默认不提交）
models/               # 训练后模型
notebooks/            # 探索与复现笔记本
reports/figures/       # 评估、SHAP 及子结构图
scripts/               # 环境检查及后续命令行入口
src/                   # 标准化、特征、模型、评估与解释模块
tests/                 # 自动化测试
app.py                 # Streamlit 入口（后续阶段实现）
```
