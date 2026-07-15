深化方向可以是：

```text

不同特征视角是否捕捉不同化学规律？

descriptor 模型、fingerprint 模型、scaffold/nearest-neighbor 模型的错误是否互补？

模型分歧能否作为“不确定性”或“需要人工审查”的信号？

```

这比“再跑一个 BiLSTM”更有价值。

你后续可以做一个 **uncertainty-aware consensus v2**：

```text

Model A: LightGBM + descriptors

Model B: RF / LightGBM + MACCS

Model C: fingerprint nearest-neighbor baseline 或 ECFP 模型

```

输出不是简单 0/1，而是：

```text

high-confidence carcinogen

high-confidence noncarcinogen

inconclusive / needs review

out-of-domain

```

这就从“分类器”升级成了“辅助筛查系统”。

### 2. 把 explainability 当作化学问题，而不是画几张 SHAP 图

原论文用了 SHAP 来寻找 MACCS keys 和 Bemis–Murcko scaffolds 这类结构线索。([PMC][1]) 你可以吸收这个思路，但不要停留在“特征重要性排行榜”。

更好的深化是：

```text

哪些描述符推动模型判断为 carcinogen？

这些描述符是否对应分子大小、疏水性、芳香性、环系统、极性表面积？

false positive 是否集中在某类结构？

false negative 是否是某些外部集特有结构？

高风险 scaffold 是否在 train 中有类似物？

```

也就是从“模型解释”走向“化学解释”。

你现在 final model 是 `LightGBM + descriptors`，这其实非常适合解释。因为 descriptor 比 2048-bit fingerprint 更容易讲清楚。你可以做：

```text

global feature importance

SHAP summary

SHAP dependence plots

top positive descriptors

top negative descriptors

descriptor 分布对比：train vs validation vs external

错误样本的 descriptor profile

```

这个方向会比硬补 BiLSTM 更适合你现在的项目基础。

### 3. 建立 applicability domain，而不是只报 AUROC

原论文强调把模型用于 IARC 2B 这类待判断化合物，并区分 within-domain compounds。([PMC][1]) 这背后的思想是：**模型不是对所有化学空间都同样可靠。**

你现在已经有泄漏审计、nearest-neighbor、scaffold、tautomer sensitivity 的基础。下一步可以深化为：

```text

给每个预测分配一个适用域状态：

- in-domain

- near-domain

- scaffold-novel

- low-similarity external

- conflicting-neighbor

```

然后看：

```text

in-domain external AUROC 是否高于 out-of-domain？

低相似度样本是否更容易错？

scaffold novel 样本的 MCC 是否下降？

高相似但标签相反的 activity cliff 是否造成错误？

```

这会把你的项目从“模型评估”提升到“模型可靠性研究”。这也是 AI4S/化学 ML 里很核心的能力。

### 4. 把 inconclusive 当作合理输出，而不是错误

原论文 consensus 的一个重要点是允许 inconclusive，而不是强迫每个化合物都二分类。([PMC][1])

这对你的方向很有启发。毒性预测本来就存在标签噪声、物种差异、数据库冲突、结构相似但标签相反等问题。你 v1 数据阶段已经非常认真地处理了 conflict 和 uncertain；模型阶段也可以继承这种思想。

v2 可以设计：

```text

如果模型概率接近 0.5 → inconclusive

如果多个模型分歧 → inconclusive

如果 out-of-domain → inconclusive

如果 nearest neighbor 标签冲突 → inconclusive

```

然后评价两套指标：

```text

coverage：有多少样本给出明确判断

selective performance：只在明确判断样本上的 AUROC / MCC / accuracy

```

这比硬追求全体样本 accuracy 更像真实毒理筛查场景。

### 5. 把数据工程变成你的核心优势

原论文有数据清洗和去重，但你的优势是更系统：正式 release、manifest、pointer、hash、external lock、prediction digest、repeat lock。训练策略也明确规定训练入口、外部集隔离、候选模型和 validation 使用规则。

这其实可以成为你项目的主线：

> 传统 QSAR 论文往往重模型、轻数据审计；本项目尝试把可追溯数据 release、泄漏审计和外部评估锁定引入化学毒性预测流程。

这个角度很适合写进作品集，也很适合面试时讲。它体现的是“我不只是会调包训练模型，我懂得怎么让实验结论可信”。

### 6. 从“预测致癌性”扩展到“毒性建模通用框架”

不要被这篇论文绑死在 carcinogenicity 上。你现在真正练出来的是一套流程：

```text

多来源毒性数据清洗

结构标准化

标签冲突处理

split 与 leakage audit

模型训练与 external 锁定

解释和适用域分析

```

这套流程可以迁移到：

```text

Ames mutagenicity

skin sensitization

acute toxicity

hepatotoxicity

cardiotoxicity / hERG

environmental toxicity

材料安全性筛查

```

这就是你“自己的方向”可以深化的地方：**做可信 QSAR / tox ML pipeline，而不是单篇论文复刻。**

## 三、后续工作规划：不要叫“复刻 v2”，叫“研究深化 v2”

我建议你接下来分成四个阶段。

## 阶段 0：封存 v1，并写出“可信基线报告”

目标不是新结果，而是把当前成果变成一个可展示成品。

马上做：

```text

final external audit

git commit

tag final-model-external-v1

final_model_v1_summary.md

```

报告核心结论写成：

```text

在严格数据冻结、预注册候选选择和一次性 external 评估下，

LightGBM + descriptors 获得 validation AUROC 0.7659，

primary external AUROC 0.7194、AUPRC 0.7728、MCC 0.2878。

该结果作为后续不确定性、适用域和解释性研究的可信基线。

```

重点是“可信基线”，不是“最好模型”。

## 阶段 1：做 v1 的研究性诊断，不改模型

这一阶段只分析，不训练新 final，不用 external 调参。

建议做 5 个报告：

```text

1. validation vs external 性能落差分析

2. descriptor 分布漂移分析

3. external 错误类型分析

4. scaffold / similarity / applicability domain 分层评估

5. LightGBM descriptor SHAP 解释

```

注意措辞：external 错误分析只能作为“post hoc analysis”，不能用于回头改 v1。

最值得做的是 applicability domain 分层。比如：

```text

按 external 到 train 的最大 ECFP4 similarity 分桶：

0.85+

0.70–0.85

0.50–0.70

<0.50

分别报告 AUROC、MCC、coverage、错误数。

```

如果你发现 in-domain 表现明显更好，那这个项目立刻就从“跑模型”变成了“解释为什么外测下降”。

## 阶段 2：做 uncertainty-aware consensus，但只在 development 内设计

这一阶段吸收原论文 consensus 的思想，但换成你的研究问题。

不要目标设为“复刻三模型 consensus”，而是设为：

> 在不牺牲 external 隔离的前提下，模型分歧和适用域信息能否识别低可信预测？

可做三个版本：

```text

Consensus A：LightGBM descriptors + RF MACCS + RF descriptors

Consensus B：descriptor model + MACCS model + ECFP model

Consensus C：model probability + nearest-neighbor agreement + applicability domain

```

输出三类：

```text

positive

negative

inconclusive

```

评价指标：

```text

coverage

covered-set AUROC

covered-set MCC

inconclusive rate

错误拦截率

```

这比单纯问“AUROC 高没高”更有研究价值。毒性预测中，能识别“我不确定”本身就是有用能力。

## 阶段 3：把解释结果变成化学假设

这一步最能体现“化学 + 机器学习”的结合。

围绕 final descriptor model 和未来 consensus model，做：

```text

高 SHAP 正向 descriptor：对应什么化学性质？

高风险 scaffold：是否富集芳香环、多环、卤素、疏水性？

false positive 是否是结构上像 carcinogen 但标签为 negative？

false negative 是否缺少 train 中类似结构？

activity cliff pair 是否集中在某些 scaffold？

```

最终产出不是“模型解释图”，而是几条化学语言的结论，例如：

```text

模型更倾向于把高芳香性、高疏水性、较大环系统的化合物判为高风险；

低相似度 external 分子和结构近邻标签冲突分子是主要错误来源；

descriptor-only 模型在 external 上保留了一定泛化能力，但对特定 scaffold novel 化合物可靠性下降。

```

这才是你方向上的深化。

## 阶段 4：抽象成一个可迁移 tox-ML 框架

最后，把这个项目从“致癌性”抽象成：

```text

Trustworthy RDKit-based Toxicity Modeling Workflow

```

模块包括：

```text

data audit

label resolution

structure standardization

leakage-safe split

feature registry

model registry

external lock

applicability domain

uncertainty / inconclusive output

interpretability report

```

之后你换任务时，比如 Ames 或 hERG，就不是从零开始，而是复用这套框架。

这会非常适合作品集，因为它显示你有“做系统”的能力。

## 四、我建议的实际执行顺序

### 现在立刻做

```text

1. 封存 v1

2. 写 final_model_v1_summary.md

3. 写一页 method_takeaways_from_paper.md

```

`method_takeaways_from_paper.md` 不要写“原论文还做了什么我没做”，而写：

```text

从论文吸收的可迁移思想：

- complementary representations

- consensus as uncertainty handling

- inconclusive output

- SHAP / scaffold interpretation

- applicability domain

- deployment-oriented prediction workflow

```

### 接下来一周

做 v1 诊断报告：

```text

descriptor SHAP

external error analysis

similarity / scaffold stratified metrics

domain-aware performance report

```

这周不要训练新模型。

### 第二周

开始 development-only consensus 实验：

```text

RF MACCS

RF descriptors

LightGBM descriptors

probability agreement

inconclusive policy

coverage-performance curve

```

如果这一步做得好，你的项目深度会明显超过“普通 QSAR baseline”。

### 第三周以后

再决定要不要补：

```text

E-state

graph model

SMILES model

new toxicity endpoint

small demo app

```

这些都不是当前最急的。

## 五、你现在最应该避免的坑

不要把“深化”理解成“再多跑几个模型”。你的 v1 已经证明你能跑模型了。后面真正有价值的是：

```text

为什么模型在 external 上下降？

哪些样本可靠？

哪些样本不该强行判断？

哪些结构信号驱动预测？

这套流程能不能迁移到其他毒性终点？

```

也不要用 external 错误来改 v1。可以分析，但不能调参。否则你前面辛辛苦苦建立的 external lock 就被自己破坏了。