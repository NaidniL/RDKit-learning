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
