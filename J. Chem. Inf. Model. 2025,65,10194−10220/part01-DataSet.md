# Part 01. Dataset Construction and Molecular Representation

## 0. 本部分目标

本部分用于记录论文中使用的数据集与分子表示方法，并在此基础上设计个人复刻与扩展方案。

文档分为两部分：

1. **论文方法整理**：总结原论文使用的数据来源、分子指纹、SMILES 表示和分子描述符。
2. **个人复刻方案**：在论文基础上重新设计数据池、训练/验证划分、外部测试集和清洗流程。

---

# A. 论文方法整理

## 1. 论文使用的数据集

### 1.1 致癌性建模数据集

论文主要涉及以下致癌性相关数据来源：

**CPDB, Carcinogenic Potency Database**
长期动物致癌性实验数据库，主要基于大鼠、小鼠、仓鼠等动物实验，用于记录化学物质的致癌性实验结果。

**CCRIS, Chemical Carcinogenesis Research Information System**
化学致癌性研究信息系统，包含化学物质的致癌性、致突变性、促肿瘤活性、肿瘤抑制作用等试验结果。

**ISSCAN, Istituto Superiore di Sanità Carcinogenicity and Mutation Database**
包含针对大鼠、小鼠等实验动物的长期致癌性实验数据，同时与致突变性数据相关。

### 1.2 论文外部测试集

论文使用了独立外部测试集，用于检验模型在训练数据之外的泛化能力。

外部测试集包括：

**ISSCAN 中的小测试集**
经过与训练集去重后，用作外部测试。

**IRIS, Integrated Risk Information System**
美国 EPA 的综合风险信息系统，包含化学物质的人类健康风险评估信息。论文中选取其中具有明确致癌性分类的条目。

**IARC, International Agency for Research on Cancer**
国际癌症研究机构的致癌物分类系统。论文中选取明确类别的化合物，并进行人工核查。

### 1.3 可能的致癌物集合

**IARC Group 2B**
IARC 2B 类表示“可能对人类致癌”的物质。论文中将其作为可能致癌物集合，用于进一步预测和分析。

---

## 2. 论文使用的分子表示方法

论文中使用多种分子表示方式，包括分子指纹、SMILES 序列和分子描述符。

### 2.1 四种分子指纹

**ECFP, Extended-Connectivity Fingerprints**
基于 Morgan 算法生成的圆形分子指纹。论文中使用 radius = 10，bit vector length = 4096。

**MACCS, Molecular ACCess System Keys**
由 167 位预定义结构键组成，表示特定化学子结构是否存在。

**RDKit Topological Fingerprint**
基于分子图路径的拓扑指纹。论文中使用固定长度位向量，长度为 2048。

**E-state, Electrotopological State Fingerprint**
基于 electrotopological state 的原子类型特征。论文中使用 79 维连续向量，可理解为一组固定原子类型的 E-state 特征统计。

---

### 2.2 SMILES 序列表示

论文中将 SMILES 作为序列输入深度学习模型。

原始方案为字符级分词：

1. 遍历 SMILES 字符，建立字符级词汇表。
2. 将每个 SMILES 转换为整数序列。
3. 设置固定序列长度为 100。
4. 长度小于 100 的序列使用 padding 补齐。
5. 长度大于 100 的序列进行截断。

---

### 2.3 十二种分子描述符

论文中使用 12 种常见 RDKit 分子描述符：

**MolWt**
Molecular weight，分子量。

**LogP**
Log of partition coefficient，正辛醇/水分配系数的对数。

**NumHDonors**
Number of hydrogen bond donors，氢键供体数量。

**NumHAcceptors**
Number of hydrogen bond acceptors，氢键受体数量。

**TPSA**
Topological polar surface area，拓扑极性表面积，主要反映 N/O 等极性原子及其相连氢原子的表面积贡献。

**NumRotatableBonds**
Number of rotatable bonds，可旋转键数量。

**NumAromaticRings**
Number of aromatic rings，芳香环数量。

**NumSaturatedRings**
Number of saturated rings，饱和环数量。

**NumHeteroatoms**
Number of hetero atoms，除 C/H 以外的杂原子数量。

**RingCount**
Number of rings，环数量。

**HeavyAtomCount**
Number of heavy atoms，除氢以外的重原子数量。

**NumAliphaticRings**
Number of aliphatic rings，脂肪环数量。

---

# B. 个人复刻与扩展方案

## 3. 数据集构建目标

在论文方法基础上，个人复刻不直接照搬论文划分，而是构建一个更完整的致癌性预测数据池。

目标是整合多个公开数据源，经过 RDKit 标准化、去重、标签统一和冲突处理后，建立一个可用于模型训练、验证和外部测试的 benchmark。

---

## 4. 数据来源设计

### 4.1 Development Pool

Development pool 用于训练模型、选择特征、调节超参数和选择分类阈值。

计划整合以下数据源：

```text
CPDB + IRIS
```

这两个数据源经清洗后合并为：

```text
development_pool.csv
```

### 4.2 外部测试集

外部测试集不参与训练、特征选择、超参数调节或阈值选择，只用于最终泛化能力评估。

计划使用：

```text
CCRIS 中与 development pool 不重合的 clear carcinogenicity records
```

筛选原则：

1. 只保留明确 carcinogenicity endpoint。
2. 排除 mutagenicity-only、tumor promotion-only、tumor inhibition-only 记录。
3. 排除 equivocal、inconclusive、inadequate 记录。
4. 排除无有效小分子结构的记录。
5. 排除与 development pool 标准 InChIKey 重合的化合物。

最终得到：

```text
external_ccris_test.csv
```

### 4.3 可选挑战集

IARC Group 2B 可作为“可能致癌物”挑战集，用于最后定性分析，而不参与训练或调参。

可选扩展：

```text
IARC Group 1 / 2A / 2B
NTP Report on Carcinogens
```

其中 IARC Group 2B 可用于观察模型对“可能致癌物”的预测倾向。

---

## 5. 数据目录结构

项目数据目录设计如下：

```text
carcinogenicity_benchmark/
├── raw/
│   ├── cpdb_raw.csv
│   ├── iris_raw.csv
│   └── ccris_raw.csv
│
├── processed/
│   ├── development_pool.csv
│   ├── train.csv
│   ├── validation.csv
│   ├── external_ccris_test.csv
│   ├── conflict_set.csv
│   └── uncertain_set.csv
│
├── features/
│   ├── train_rdkit_descriptors.csv
│   ├── train_maccs.csv
│   ├── train_ecfp.csv
│   ├── train_estate.csv
│   └── train_smiles_tokens.npy
│
└── reports/
    ├── overlap_report.csv
    ├── split_report.csv
    └── cleaning_log.md
```

---

## 6. 数据处理流程

整体流程如下：

```text
raw data
→ source-specific cleaning
→ RDKit standardization
→ parent molecule extraction
→ canonical SMILES / standard InChIKey
→ label harmonization
→ conflict removal
→ development pool construction
→ train / validation split
→ external test filtering
```

具体步骤：

### 6.1 来源内清洗

对每个数据源单独处理：

1. 统一字段名。
2. 提取 CAS、name、raw SMILES、原始标签、endpoint、source。
3. 去除明显缺失结构或缺失标签的记录。
4. 保留原始标签，不直接覆盖。

### 6.2 RDKit 分子标准化

对所有分子进行统一标准化：

1. `Chem.MolFromSmiles()` 检查 SMILES 合法性。
2. 提取最大有机片段或 parent molecule。
3. 处理盐、混合物和无机物。
4. 生成 canonical SMILES。
5. 生成 standard InChIKey。
6. 生成 Murcko scaffold。
7. 标记无法解析或不适合建模的记录。

### 6.3 标签统一

将不同来源的原始标签统一为：

```text
positive
negative
uncertain
conflict
excluded
```

第一版二分类任务只保留：

```text
positive → 1
negative → 0
```

以下记录暂不进入主训练集：

```text
uncertain
conflict
equivocal
inconclusive
inadequate
mixture
polymer
inorganic
no valid structure
```

### 6.4 标签冲突处理

以 standard InChIKey 为单位聚合同一结构的多条记录。

处理原则：

1. 如果所有 clear records 均为 positive，则标记为 positive。
2. 如果所有 clear records 均为 negative，则标记为 negative。
3. 如果同一 InChIKey 同时存在 clear positive 和 clear negative，则进入 conflict_set.csv。
4. 如果只有 uncertain / equivocal / inadequate，则进入 uncertain_set.csv。
5. 如果 IRIS 与动物实验标签不一致，保留原始来源信息，并优先人工核查。

---

## 7. 训练集与验证集划分

### 7.1 Development Pool

```text
development_pool =  CPDB + IRIS
```

### 7.2 划分方式

第一版采用：

```text
label-stratified random split
train : validation = 80 : 20
```

第二版升级为：

```text
Murcko scaffold group split
train : validation = 80 : 20
```

划分单位：

```text
Murcko scaffold
```

划分后检查以下分布：

```text
label_binary
source
molecular weight
Murcko scaffold overlap
```

要求：

1. train 和 validation 之间不能有相同 standard InChIKey。
2. scaffold split 版本中，train 和 validation 尽量避免共享相同 Murcko scaffold。
3. validation 不参与模型训练，只用于模型选择和阈值选择。

### 7.3 外部测试集冻结

```text
external_ccris_test.csv
```

只在最终模型确定后使用。

external test 不参与：

```text
feature selection
hyperparameter tuning
threshold selection
model calibration
error-driven cleaning
```

---

## 8. 分子表示复刻与扩展

### 8.1 论文复刻特征

复刻论文中的以下分子表示：

```text
ECFP
MACCS
RDKit topological fingerprint
E-state fingerprint
12 RDKit molecular descriptors
SMILES sequence
```

### 8.2 ECFP 参数

论文复刻参数：

```text
Morgan radius = 10
nBits = 4096
```

扩展对照参数：

```text
Morgan radius = 2, nBits = 2048
Morgan radius = 3, nBits = 2048
Morgan radius = 2, nBits = 4096
```

### 8.3 RDKit Topological Fingerprint

使用 RDKit 拓扑路径指纹。

复刻参数：

```text
fpSize = 2048
```

第一版使用 RDKit 默认路径参数，后续可进行参数敏感性分析。

---

## 9. SMILES 分词扩展

论文使用字符级 SMILES 分词。个人复刻中计划将字符级分词替换为基于正则表达式的 SMILES tokenization。

### 9.1 Regex Tokenizer

优先匹配：

```text
bracket atom: \[[^\]]+\]
two-character atoms: Br, Cl, Si, Na, Li, Al, Ca, Fe 等
ring closure: %\d\d 或单个数字
bond symbols: =, #, -, /, \
branch symbols: (, )
aromatic atoms: b, c, n, o, p, s
single-character atoms and symbols
```

### 9.2 序列长度处理

固定序列长度：

```text
max_len = 100
```

处理规则：

```text
token length <= 100:
  padding 到 100

token length > 100:
  保留前 50 个 token + 后 50 个 token
```

该方案用于尽量保留 SMILES 的首尾信息，但可能丢失中间结构信息。因此后续可与以下方案对照：

```text
直接保留前 100 个 token
max_len = 150
max_len = 200
```

---

## 10. 输出文件

最终输出以下数据文件：

```text
processed/development_pool.csv
processed/train.csv
processed/validation.csv
processed/external_ccris_test.csv
processed/conflict_set.csv
processed/uncertain_set.csv
```

每个 processed 数据表建议包含以下字段：

```text
compound_id
source
source_record_id
casrn
name
raw_smiles
canonical_smiles
parent_smiles
standard_inchikey
murcko_scaffold
label_raw
label_binary
label_category
label_confidence
endpoint
species
route
reference
rdkit_mol_ok
standardization_notes
```

---

## 11. 可复现性记录

为了保证数据集构建过程可复现，需要记录：

```text
RDKit version
Python version
data download date
raw file checksum
standardization rules
label mapping rules
random seed
split method
train / validation label distribution
train / validation source distribution
external overlap report
```

输出报告：

```text
reports/cleaning_log.md
reports/overlap_report.csv
reports/split_report.csv
```
