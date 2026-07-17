# RDKit Learning

一组面向 RDKit 初学与实验的 Jupyter Notebook。项目通过可直接运行的示例，演示分子绘图、分子属性计算、子结构匹配、分子哈希、化学反应处理以及非默认价态检查等常用功能。

## 内容

| Notebook | 主要内容 |
| --- | --- |
| `0-draw-a-mol.ipynb` | 分子与反应绘图、原子/键索引、立体标注、高亮、缩写基团与大分子二维布局 |
| `1-simple-cal.ipynb` | Gasteiger 部分电荷、杂化类型、环系统、手性与双键立体信息、侧链及 R 基枚举 |
| `2-match-a-subfracture.ipynb` | SMARTS 子结构查询、匹配高亮、最大公共子结构（MCS）、大环与精确键匹配 |
| `3-mol-hash.ipynb` | `rdMolHash`、Murcko 骨架、区域异构体哈希与哈希片段可视化 |
| `4-reaction.ipynb` | 反应 SMARTS、正向/逆向反应绘图与反应差异指纹相似度 |
| `5-not-default.ipynb` | 绕过默认价态检查、局部清洗、化学问题检测与过渡金属配位键转换 |

## 环境要求

- Python 3.10+
- RDKit
- JupyterLab

其余 Python 依赖已列在 `requirements.txt` 中。

## 安装与运行

```bash
git clone https://github.com/NaidniL/RDKit-learning.git
cd RDKit-learning

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

jupyter lab
```

Windows PowerShell 中激活虚拟环境时使用：

```powershell
.venv\Scripts\Activate.ps1
```

启动 JupyterLab 后，建议按文件名前的数字顺序打开 Notebook。每个 Notebook 都可独立运行，也可作为查询 RDKit API 用法的示例集。

## 说明

本项目用于 RDKit 学习与实验。Notebook 中的分子、反应及计算结果仅作为编程示例，不应直接用于科研或药物决策。

## 独立项目：化学致癌性预测

仓库同时包含一个独立、可审计的研究项目：[`J. Chem. Inf. Model. 2025,65,10194−10220`](<J. Chem. Inf. Model. 2025,65,10194−10220/>)。该项目以 RDKit、LightGBM 与 Random Forest 建立致癌性预测工作流，覆盖多来源数据治理、结构标准化、标签冲突处理、development/external 隔离、冻结训练工件和一次性外部评估。

当前冻结结论：

- v1 是已封存的单模型基线；其 CCRIS primary external 只评估一次。
- v2 是三成员 selective consensus（全体同意才给二分类，否则 `inconclusive`）。已完成独立 NTP external 验证，但最终状态为 **`PARTIAL_SUCCESS`**：coverage `0.653061`，covered MCC `0.647150`，而 covered sensitivity `0.625000` 低于预注册下限 `0.65`。
- 该结论不能写成“v2 验证成功”“优于 v1”或“可用于致癌物筛查”。完整边界、审计和 Wilson 描述性区间见项目内的[最终发布目录](<J. Chem. Inf. Model. 2025,65,10194−10220/reports/modeling/final_consensus_v2_evaluation_v1/>)与[阶段总结](项目阶段总结_化学致癌性预测.md)。

进入项目、安装环境和查看可复现入口请阅读其 [README](<J. Chem. Inf. Model. 2025,65,10194−10220/README.md>)。
