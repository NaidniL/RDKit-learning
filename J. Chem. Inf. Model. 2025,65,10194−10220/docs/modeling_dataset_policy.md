# 建模数据集组装、泄漏审计与 split v1 策略（待审查稿）

本文档规定阶段 2 的数据集组装、化合物级解析、数据划分、泄漏审计和冻结规则。
本阶段不生成特征、不训练模型，也不修改阶段 1 已冻结的 `data/processed/`。

## 1. 冻结基线与范围

阶段 2 只接受以下清洗冻结点作为输入：

- Git 标签：`dataset-cleaning-v1`；
- 正式清洗 run-id：`20260704_130911_599434_UTC_a2cf0ca3`；
- 批准的清洗审计 run-id：`20260704_125032_638051_UTC_a2cf0ca3`；
- 清洗输入指纹：
  `a2cf0ca354b4d3cbaee8e8b37e4de0afb481fa633a59341ed0f33f281784e93d`。

`data/processed/` 是只读输入。组装程序不得覆盖、修补或重新解释其中任何文件；若发现
阶段 1 的错误，应回到新的清洗版本，而不是在阶段 2 静默更正。

### 1.1 13 张清洗表的使用方式

不得把 13 张 CSV 直接纵向拼接。它们包含来源记录、化合物聚合结果、划分结果和排除视图，
直接拼接会重复计算同一证据。

- `source_records_audit.csv` 是来源级事实表，用于构建 `records_all.csv`；
- `development_pool.csv`、`external_ccris_test.csv`、`conflict_set.csv`、
  `uncertain_set.csv` 和各 review candidate 表是阶段 1 的化合物级决策视图；
- `excluded_set.csv` 提供排除原因和仍需参与泄漏拦截的结构键；
- `structure_representation_conflict.csv` 提供结构表示异常；
- `train.csv` 和 `validation.csv` 只用于核对论文复刻划分，不作为来源记录再次输入。

组装程序必须核对这些派生视图与来源事实表之间的一致性。任何无法解释的缺失、增量或标签
变化均使组装失败。

## 2. 统一建模端点与证据语义

### 2.1 主任务标签

主任务为化学物质致癌危害的严格二分类：

```text
1 = carcinogen
0 = noncarcinogen
```

只允许阶段 1 中 `label_category=positive/negative` 且 `label_confidence=high` 的致癌性证据
产生 `normalized_label`。这两种组合在本文中简称“明确阳性”和“明确阴性”。ambiguous、
equivocal、inadequate、not classifiable、suggestive、
probable、possible、部分阳性、带限定语结果以及非致癌性终点不得被强制映射为 0 或 1。

### 2.2 来源标签映射

| 来源 | `normalized_label=1` | `normalized_label=0` | 不进入主任务 |
|---|---|---|---|
| CPDB | 原始代码 `+`、`c` 且试验充分 | 原始代码 `-` 且试验充分 | `p`、`a`、`e`、`0`、空值、`inad=i` 及其他非明确类别 |
| IRIS | `A (Human carcinogen)`、`Carcinogenic to humans` | `E (Evidence of non-carcinogenicity for humans)` | probable、possible、likely、suggestive、D 类、证据不足、无法分类及带条件的 not likely |
| CCRIS | 致癌性试验结果规范化后严格等于 `POSITIVE` | 致癌性试验结果规范化后严格等于 `NEGATIVE` | 带限定语结果、非致癌性终点、方向不明或证据不足结果 |

上述规则必须从阶段 1 的 `label_raw`、`label_category`、`label_candidate`、
`label_confidence` 和 `label_reason` 重建并断言一致，不得只相信最终 `label_binary`。

### 2.3 多物种、多性别和多实验聚合

来源级记录不先按物种、性别或试验次数多数投票。标签必须先在数据角色内独立解析：development
只使用 CPDB/IRIS 证据，external 只使用 CCRIS 证据。对同一角色内的同一标准化结构：

1. 所有明确阳性且无明确阴性：解析为 1；
2. 所有明确阴性且无明确阳性：解析为 0；
3. 明确阳性与明确阴性并存：标记 `exact_duplicate_conflicting_label`；
4. 只有不确定或候选证据：不进入主任务；
5. 明确标签与相反方向弱证据并存：保留明确标签，同时标记
   `discordant_nonclear_evidence`，进入敏感性分析清单。

弱证据不得推翻明确证据，也不得用于打破明确标签冲突。冲突不能按来源数、记录数或数据库数
多数投票后静默解决。

跨角色证据永不共同投票。若同一完整结构同时出现在 development 与 external，development 标签
只由 CPDB/IRIS 解析，CCRIS 记录只进入跨角色重复与泄漏审计；CCRIS 标签不得改写、确认或冲突化
development 标签。只有通过 development 泄漏隔离的 external-only 结构，才用 CCRIS 证据解析
external 标签。

### 2.4 人体与动物证据

Scheme C v1 延续阶段 1 的角色定义：CPDB 和严格 IRIS 证据构成 development pool，
严格 CCRIS 证据构成 external evaluation pool。人体证据和动物证据允许共同服务于“致癌危害”
主任务，但必须保留 `evidence_type`、物种、来源和证据层级，不得将其伪装为同一种实验。

必须分别报告来源和证据类型的类别分布，并执行第 7 节定义的确定性来源偏倚统计；若来源与标签
高度关联，应视为数据偏倚信号。不得将 `source_dataset`、`evidence_type`、物种或来源 ID 用作
正式结构模型特征。

external test 的 0/1 语义必须与 development 完全相同，但来源证据体系可以不同；该差异必须在
数据概况和局限性中披露。

`evidence_type` 使用受控枚举：所有 IRIS 致癌分类记录（包括非二分类和候选类别）均为
`human_weight_of_evidence`；有明确实验动物物种的 CPDB/CCRIS 记录为
`animal_experimental`；无法从来源字段可靠判定物种的 CPDB/CCRIS 实验记录为
`experimental_unspecified`。标签是否进入主任务只由 `label_rule` 决定，不由 evidence type 决定。
不得根据化合物名称或最终标签猜测证据类型。`records_all.csv` 每行必须恰好有一个非空且合法的
`evidence_type`。

## 3. 来源级与化合物级数据模型

### 3.1 `records_all.csv`

`records_all.csv` 每行对应一条阶段 1 来源记录，不因标签、可建模性或 split 资格而删除。必须无损
保留 `source_records_audit.csv` 的全部原列、原始文本和 JSON 字段，再新增以下别名或派生字段：

```text
record_key
source_dataset
source_record_id
source_chemical_id
source_label
normalized_label
label_rule
label_confidence
evidence_type
endpoint
species
route
reference
canonical_smiles
parent_smiles
standardized_inchikey
connectivity_key
murcko_scaffold
model_structure_ok
exclusion_reason
cleaning_run_id
```

`record_key` 固定为 `source_dataset + ":" + source_record_id`。两部分均不得为空，组合键必须唯一。
`source_label` 保留原始标签文本；`label_rule` 使用受控代码指明映射规则，不能只写自由文本。
原表中的 `source_payload_json`、`structure_provenance`、`raw_smiles`、
`leakage_connectivity_keys_json` 和人工无机碳审核字段不得删除或摘要化。

`label_rule` 只允许：

```text
cpdb_clear_positive
cpdb_clear_negative
iris_human_positive
iris_human_negative
ccris_exact_positive
ccris_exact_negative
nonbinary_uncertain
noncarcinogenicity_endpoint_only
```

每条记录必须命中且只命中一个标签规则。无法映射的新来源值直接失败，不允许使用
`unknown` 或默认阴性兜底。

### 3.2 `compounds_resolved.csv`

该表一化合物一行。`compound_id` 固定为：

```text
CMP:<standardized_inchikey>
```

该 ID 与数据角色和 split 无关，可直接复算且不会因来源增加而改变。输入 InChIKey 必须符合
标准格式；重复 `compound_id` 立即失败。多种来源表示按下述已知冲突规则处理，不能任取第一行。

至少包含：

```text
compound_id
canonical_smiles
parent_smiles
source_canonical_smiles_json
parent_smiles_variants_json
standardized_inchikey
connectivity_key
nonisomeric_parent_smiles
tautomer_family_key
murcko_scaffold
normalized_label
source_datasets_json
source_record_keys_json
source_labels_json
evidence_types_json
primary_role
label_resolution_record_keys_json
label_resolution_sources_json
nonresolution_record_keys_json
resolution_status
resolution_rule
split_eligibility
cleaning_run_id
```

所有 JSON 数组先去重再按 Unicode 字典序排序，使用固定 JSON 序列化参数。来源增加不得覆盖旧来源。
`primary_role` 只允许 `development` 或 `external`。同一完整键跨角色时取 `development`；
`label_resolution_record_keys_json` 只能包含该 primary role 中实际参与标签解析的明确证据，其他角色、
弱证据和非致癌性终点进入 `nonresolution_record_keys_json`。程序必须断言两个集合无交集且并集可
回溯到该 compound 的全部来源记录。

只有能够生成有效 `standardized_inchikey` 的来源记录才能形成 `compound_id` 并进入
`compounds_resolved.csv`。无有效键的记录只保留在 `records_all.csv` 和 record-level 排除统计中。
`excluded_structure` 仅用于“已有有效标准键、但因混合物等阶段 1 规则不可建模”的 compound，
不能为无键记录伪造 ID。

结构代表字段按以下规则生成：

1. `source_canonical_smiles_json` 保留该键全部非空来源 `canonical_smiles`；
2. `parent_smiles_variants_json` 保留全部非空 `parent_smiles`；
3. 若 parent 变体恰好一个，`parent_smiles` 取该唯一值，`canonical_smiles` 由该 parent 重新解析后用
   RDKit `MolToSmiles(canonical=True, isomericSmiles=True)` 生成，不得从来源 canonical 值任选；
4. 若 parent 变体多于一个，必须与冻结的 `structure_representation_conflict.csv` 中同一 InChIKey
   声明的变体集合完全一致。该 compound 保留在主表中，但 `canonical_smiles`、`parent_smiles`、
   `nonisomeric_parent_smiles` 和 `tautomer_family_key` 留空，设置
   `resolution_status=excluded_structure`、`resolution_rule=structure_ineligible`、
   `split_eligibility=ineligible_structure`；
5. 任何未在阶段 1 冲突表声明的新多 parent 键、已声明键缺失、变体集合不一致或声明出现额外键，
   均使组装失败。

因此，冻结数据中已知的 4 个结构表示冲突应被确定性承接并排除，而不是作为新错误中止；来源
canonical 多值但 parent 唯一时不构成结构冲突，全部来源表示仍由 JSON 字段保留。

### 3.3 解析状态与排除表

`resolution_status` 只允许：

```text
resolved
manual_review_required
excluded_conflict
excluded_uncertain
excluded_structure
excluded_leakage
```

无法获得唯一二分类标签的结构不得出现在 `compounds_resolved.csv` 的可划分子集中。冲突、人工
决策和排除轨迹写入 `excluded_conflicts.csv`，其中保留全部来源键、证据 JSON、规则、审核决定、
理由、审核人和时间。若启用人工冲突解析，唯一机器可读输入为：

```text
data/manual/modeling_conflict_decisions.csv
```

模板字段固定为 `compound_id, decision, review_reason, reviewer, reviewed_at_utc`。

split v1 不允许在阶段 2 将阶段 1 已排除的冲突重新纳入 development。确定性标签冲突默认按
`exact_label_conflict_exclude` 自动排除；人工文件仅用于追加 `confirm_exclude` 审核决定，不得把
冲突改为阳性或阴性。所有人工决定必须有理由和审核人；空值、未知 compound ID、重复决定或
`confirm_exclude` 之外的决定都会阻止正式组装。未人工确认的冲突仍按明确策略排除，不是 pending。
若未来需要把冲突纳入主 split，必须回到新的清洗/组装策略版本，不能继续称为 split v1。

人工决策模板还必须包含必填 `reviewed_at_utc`，使用带时区的 RFC 3339 UTC 字符串。审核时间是
固定输入的一部分；程序不得用运行时当前时间填充记录，否则相同输入不能产生相同输出哈希。

`resolution_rule` 只允许：

```text
unanimous_clear_positive
unanimous_clear_negative
exact_label_conflict_exclude
manual_confirmed_conflict_exclude
no_clear_binary_label
structure_ineligible
external_exact_leakage
external_connectivity_leakage
```

`split_eligibility` 只允许 `eligible`、`ineligible_label`、`ineligible_structure`、
`ineligible_conflict`、`ineligible_leakage`。状态、规则和资格之间的合法组合必须用表驱动校验。

## 4. 跨来源重复和结构关系审计

### 4.1 等价层次与受控分类

按以下顺序分类，每组只使用第一个适用的主分类，并可附加次级标志：

1. 完整 `standardized_inchikey` 相同，在角色内分别判断标签：
   `exact_duplicate_same_label` 或 `exact_duplicate_conflicting_label`；
2. 完整键不同但 `connectivity_key` 相同，且清除立体/同位素标记后的 parent 相同：
   `stereo_variant_same_label` 或 `stereo_variant_conflicting_label`；
3. RDKit 规范互变异构后属于同一 `tautomer_family_key`：`tautomer_related`；
4. Morgan/ECFP4 Tanimoto 相似度不低于 0.85：
   `high_similarity_same_label` 或 `high_similarity_opposite_label`；
5. 不满足以上关系：`unique`。

跨角色的同结构或相关结构另加 `cross_role_overlap`；若两角色各自解析出的标签相反，再加
`cross_role_label_disagreement`。这些次级标志只用于审计，不参与 development 标签投票。

`nonisomeric_parent_smiles` 和 `tautomer_family_key` 的算法、RDKit 版本和参数必须进入输入指纹。
结构算法失败时不得降级为名称或 CASRN 去重。

`nonisomeric_parent_smiles` 从阶段 1 的 `parent_smiles` 解析：清除原子手性、双键立体标记和同位素
编号后，以 `canonical=True, isomericSmiles=False` 生成 SMILES。`tautomer_family_key` 在该分子上
使用与阶段 1 相同配置的 RDKit `TautomerEnumerator` 生成 canonical tautomer，再生成 canonical
non-isomeric SMILES，并定义为 `TAU:` 加该 SMILES UTF-8 字节的完整 SHA-256。空值或算法失败必须
显式报告，不能用原字符串或名称兜底。配置显式调用 `SetRemoveSp3Stereo(False)` 和
`SetReassignStereo(True)`，其余参数保持已锁定 RDKit 版本的默认值并写入 runtime signature。

ECFP4 固定使用 RDKit `GetMorganFingerprintAsBitVect`：`radius=2`、`nBits=2048`、
`useChirality=True`、`useBondTypes=True`、`useFeatures=False`、
`includeRedundantEnvironments=False`。Tanimoto 使用 RDKit `DataStructs.TanimotoSimilarity`。
指纹输入固定为阶段 1 的标准化 `parent_smiles`，保留其手性信息。

结构关系和高相似 pair 的比较宇宙固定为 `compounds_resolved.csv` 中具有可解析 `parent_smiles`、
且 `resolution_status != excluded_structure` 的全部 compound，包括 resolved、conflict、uncertain
和 leakage 状态。每个无序 pair 只保留一次：两个 `compound_id` 按 Unicode 字典序记为
`compound_id_a < compound_id_b`；报告按关系优先级、`compound_id_a`、`compound_id_b` 排序。

### 4.2 解析原则

- 完全相同结构且标签相同：合并来源；
- 完全相同结构但标签冲突：人工审核或排除，不多数投票；
- stereo、tautomer 或高相似关系：默认不合并成一个化合物；
- 非完全相同结构的异标签关系不用于自动改标签；
- 同 connectivity 的不同结构不得跨 development 与 external；
- 高相似异标签对作为 activity-cliff 候选永久报告；
- 结构关系图的连通分量、成员、边类型和阈值必须可追溯。

至少生成：

```text
reports/dataset_assembly/current/duplicate_groups.csv
reports/dataset_assembly/current/label_conflicts.csv
reports/dataset_assembly/current/high_similarity_pairs.csv
reports/dataset_assembly/current/activity_cliff_candidates.csv
reports/dataset_assembly/current/resolution_summary.json
```

## 5. Scheme C 与 split v1

### 5.1 角色优先级

先按角色独立解析标签，再固定 development 泄漏全集，最后处理 external。development 泄漏全集
只包含 `dataset_role=development` 的有效模型结构，以及同角色被排除但仍可解析的结构键；绝不把
external 自身的 excluded 或 leakage key 加入 development 泄漏全集。任何 external 候选只要与该
development 泄漏全集存在相同 `standardized_inchikey` 或 `connectivity_key`，均从 external test
排除。不得通过先删除 development 结构来扩大 external。

最终只有同时满足 `resolution_status=resolved` 且 `split_eligibility=eligible` 的 compound 才能进入
主划分，并且必须恰好属于：

```text
primary_reproduction_split/train
primary_reproduction_split/validation
external_test
```

CV fold 是 train/development 内部的评估标注，不是第四个互斥数据角色。

### 5.2 论文复刻协议

主划分使用：

```text
sklearn.model_selection.train_test_split
train : validation = 80 : 20
random_state = 42
stratify = normalized_label
shuffle = True
```

输入顺序严格使用 `data/processed/development_pool.csv` 中 `standard_inchikey` 的现有顺序，并先断言
它已按该字段升序排列；然后调用固定版本 scikit-learn。完整 InChIKey 已在化合物解析阶段唯一化，
因此 train 与 validation 不得存在完全结构交叉。论文复刻协议允许不同立体形式的相同
`connectivity_key` 被随机分到两侧，但必须生成报告；该结果不得被描述为严格结构外推。

由于 v1 的标签与 development 资格应与阶段 1 完全一致，新生成的 train/validation InChIKey
membership 必须分别与 `data/processed/train.csv` 和 `data/processed/validation.csv` 完全相等；
任何增删或换边均使 dry-run 失败。未来若有意改变主划分，必须提升数据策略版本，不能继续称为
split v1。

最终 external test 的 `standardized_inchikey → normalized_label` 映射也必须与
`data/processed/external_ccris_test.csv` 的 `standard_inchikey → label_binary` 完全一致；任何缺失、
新增或标签变化均使 dry-run 失败。

同时为 development pool 冻结分层 5 折 CV：`StratifiedKFold(n_splits=5, shuffle=True,
random_state=42)`。输入使用与主划分相同的 development 固定顺序；fold 编号为整数 0–4，按
scikit-learn 产生顺序编号。`stratified_cv_folds.csv` 每个 development compound 恰好一行，字段固定为
`compound_id, standardized_inchikey, normalized_label, fold_id`，`fold_id` 表示该 compound 作为验证集
的折号；输出按 `standardized_inchikey` 升序排列。

### 5.3 稳健性 scaffold CV

额外生成 Bemis-Murcko scaffold 分组 5 折，不替代论文复刻随机划分。先为每个 compound 建立
基础组键：非空 Murcko scaffold 使用 `SCAFFOLD:<murcko_scaffold>`；空 scaffold 使用
`ACYCLIC:<connectivity_key>`。再构建无向图：共享非空 scaffold 或共享 `connectivity_key` 的
compound 之间连边。每个连通分量是最终 group，`group_key` 固定为该分量按 Unicode 字典序最小的
`compound_id`。同一最终 group 不得跨 fold。

确定性分配按以下顺序执行：

1. group 按样本数降序；
2. 同样本数时按阳性数降序；
3. 再按 group key 字典序；
4. 对每个候选 fold，临时加入当前 group 后计算全局分数：
   `Σ_f[((n_f-N/5)/N)^2 + ((p_f-P/5)/P)^2 + ((q_f-Q/5)/Q)^2]`，其中 `n/p/q`
   分别为 fold 的总数、阳性数、阴性数，`N/P/Q` 为全体对应数量；
5. 选择分数最小的 fold；使用 IEEE 754 双精度原值比较，不做显示精度舍入；
6. 分数完全相等时选择编号最小的 fold。

每个 fold 应包含两个类别；无法满足时组装失败并要求修改已记录的协议，禁止静默减少折数。
`scaffold_cv_folds.csv` 每个 development compound 恰好一行，字段固定为
`compound_id, standardized_inchikey, normalized_label, murcko_scaffold, group_key, fold_id`；fold 编号为
整数 0–4，输出按 `standardized_inchikey` 升序排列。

输出目录：

```text
data/splits/v1/primary_reproduction_split/train.csv
data/splits/v1/primary_reproduction_split/validation.csv
data/splits/v1/primary_reproduction_split/stratified_cv_folds.csv
data/splits/v1/robustness_scaffold_cv/scaffold_cv_folds.csv
data/splits/v1/external_test.csv
```

## 6. external test 隔离与泄漏审计

### 6.1 强制为零的交叉

正式提交前必须断言：

```text
development ∩ external_test standardized_inchikey = 0
development ∩ external_test connectivity_key = 0
train ∩ validation standardized_inchikey = 0
train ∩ external_test standardized_inchikey = 0
validation ∩ external_test standardized_inchikey = 0
```

泄漏集合必须同时包含 development 的有效模型结构，以及 `excluded_set.csv` 中
`dataset_role=development` 记录的所有可解析 `leakage_connectivity_keys_json`。不得加入
`dataset_role=external` 的排除记录。这样被排除的 development 混合物或溶剂化物不能借 external
重新进入，同时避免 external 对自身造成误排。

### 6.2 必须报告但不强制为零的关系

- train、validation 与 external 的 Murcko scaffold 重叠数和比例；
- 每个 external compound 到 development/train 的最大 ECFP4 Tanimoto 相似度；
- Tanimoto ≥ 0.85 的全部近邻对；
- 高相似但标签相反的 activity-cliff 候选；
- train 与 validation 的 connectivity overlap；
- external 各来源、证据类型、标签的数量和比例。

最大相似度计算使用与阶段 3 ECFP4 相同的 RDKit 参数；参数和实现版本进入 manifest。

### 6.3 外部集不可用于调参

external 标签可以为冻结和审计存在于文件中，但普通训练数据加载器默认不得读取
`data/splits/v1/external_test.csv`。只有显式 `evaluation_mode="external_final"` 且提供冻结 manifest
时才能加载。单元测试必须验证超参数搜索、特征选择、阈值选择、早停、校准和模型选择路径均不
接收 external 数据。

在模型定型前，报告不得输出 external 性能。对 external 的每次最终评估必须记录模型工件哈希、
split manifest 哈希和时间，避免反复查看后人工调参。

## 7. 划分后数据概况与来源偏倚

对 train、validation、external test 分别报告：

- 样本数、阳性数、阴性数和阳性率；
- 来源与证据类型组成及其标签条件分布；
- 分子量、Crippen LogP、TPSA、HBD、HBA、可旋转键、总环数、芳香环数和重原子数；
- 唯一 Murcko scaffold 数、单例 scaffold 数和比例；
- 到 train 的最大 ECFP4 相似度分布；计算 train 样本时必须排除 compound 自身，若不存在其他
  train compound 则记为缺失；
- 缺失、异常和描述符计算失败计数。

连续变量至少报告 count、missing、mean、std、min、P05、P25、median、P75、P95、max。
分布漂移同时报告标准化均值差和双样本 KS 统计量；这些是描述性诊断，不用于查看 external 后
调整 split。KS 与列联表卡方统计固定使用锁定版本的 `scipy.stats`，SciPy 版本进入 runtime
signature 和输入指纹。

必须单独生成来源-标签列联表。本阶段不训练任何模型；来源偏倚使用确定性统计诊断：将已排序的
`label_resolution_sources_json` 作为来源组合类别。该字段只根据
`label_resolution_record_keys_json` 对应的来源生成，不得把被隔离的跨角色证据或弱证据算入
development 的来源组合；`source_datasets_json` 仍无损表示该 compound 的全部来源。报告每类样本
数、阳性率和相对全体阳性率的绝对差，并计算来源组合与标签的 Cramér's V。如果任一来源组合
样本数不少于 20 且类别纯度
`max(positive_rate, 1-positive_rate)` 不低于 0.90，
或 Cramér's V 不低于 0.30，则 manifest 标记 `source_label_confounding_warning=true`。该警告不自动
改变标签或 split。

Cramér's V 使用未校正公式 `sqrt(chi2 / (n * min(r-1, c-1)))`；若分母为 0 则记为 0。
列联表行、列排序和浮点输出精度必须固定并进入实现测试。

建议输出：

```text
reports/dataset_assembly/current/split_summary.csv
reports/dataset_assembly/current/source_label_crosstab.csv
reports/dataset_assembly/current/descriptor_summary.csv
reports/dataset_assembly/current/scaffold_summary.csv
reports/dataset_assembly/current/similarity_summary.csv
reports/dataset_assembly/current/distribution_shift.csv
reports/dataset_assembly/current/leakage_audit.json
```

## 8. 可审计运行、事务提交与冻结

### 8.1 目录

```text
audits/dataset_assembly/<run-id>/
reports/dataset_assembly/current/
data/modeling/v1/
data/splits/v1/
```

dry-run 的全部拟发布数据和报告都保存在唯一审计目录，不能写入三个正式目录。确定性 artifacts
包括 modeling CSV、split CSV、关系/统计 CSV 及确定性 JSON 报告；run-specific envelope 只包括
manifest 和运行日志。正式运行使用 `--approved-audit-run <run-id>`，先验证审计目录，再重新计算
全部确定性 artifacts 并与批准审计逐文件比较哈希、字节数、行数和文件集合，最后以目录级事务
同时替换正式 modeling、splits 和 current reports。任何不一致均不得留下部分正式输出。

正式 manifest 和日志必须重新生成，以记录新的正式 run-id、`run_type=formal`、批准的 audit
run-id 和正式运行时间，因此不要求与 dry-run 的 manifest/log 同哈希。正式 manifest 中的输入
指纹、runtime signature、settings、确定性 output/report maps 必须与批准审计一致；正式日志必须
由正式 manifest 记录并校验自身哈希。正式运行前还必须按审计 manifest 校验审计目录自身的全部
文件集合、确定性 artifacts 哈希/行数及审计日志哈希，防止批准后被篡改。

### 8.2 输入指纹

输入指纹至少覆盖：

- `dataset-cleaning-v1` 对应的 Git commit 和正式 cleaning manifest；
- 13 个 `data/processed/*.csv` 的路径、SHA-256 和行数；
- 本策略文档、组装模块、入口脚本和全部相关测试；
- 人工冲突决策文件（即使只有表头）；
- split、相似度、scaffold、标签和 JSON 序列化参数；
- Python、操作系统、机器架构、RDKit、InChI、NumPy、pandas、scikit-learn、SciPy 及其实现签名；
- 随机种子和线程/并行设置。

运行 ID 使用 UTC 时间和输入指纹前缀。相同输入重跑允许 run-id 不同，但全部确定性 data/report
artifacts 的哈希必须相同；manifest 和日志因包含运行上下文可以不同。

### 8.3 Manifest

Manifest 至少记录：

- schema version、run-id、run type、批准的 audit run-id；
- cleaning 冻结点、输入指纹和运行环境签名；
- 每个输入、输出和报告的 SHA-256、字节数、CSV 行数；
- 标签映射、冲突解析和 split 参数；
- development/train/validation/external 的数量和类别分布；
- 重复组、冲突组、排除项和泄漏关系计数；
- external 锁定状态；
- 人工审核文件及其哈希。

审计目录、正式目录和 manifest 中不得出现用户主目录绝对路径或凭据。

### 8.4 人工审核与正式提交

执行顺序固定为：

```text
测试
→ dry-run
→ 审查重复组、冲突、泄漏和分布报告
→ 完成人工冲突决策
→ 若任何输入变化则重新测试和 dry-run
→ 批准最终 run-id
→ 正式运行
→ 逐文件哈希、行数和环境复核
→ 独立审核
→ Git 提交
→ 标签 modeling-dataset-v1
```

`modeling-dataset-v1` 必须指向包含正式 manifest 和报告的提交，不能移动或复用
`dataset-cleaning-v1`。大文件若不提交 Git，必须由审计目录或发布存储保存同字节副本，并在 Git
中保留哈希、行数、来源和精确重建命令。

## 9. 预期正式输出

```text
data/modeling/v1/records_all.csv
data/modeling/v1/compounds_resolved.csv
data/modeling/v1/excluded_conflicts.csv

data/splits/v1/primary_reproduction_split/train.csv
data/splits/v1/primary_reproduction_split/validation.csv
data/splits/v1/primary_reproduction_split/stratified_cv_folds.csv
data/splits/v1/robustness_scaffold_cv/scaffold_cv_folds.csv
data/splits/v1/external_test.csv
```

除上述核心文件外，可以增加关系边表、人工审核候选表和诊断报告，但必须进入 manifest，不能产生
未登记的临时结果。

## 10. v1 验收条件

- [ ] 每个进入 split 的建模化合物恰好一个最终二分类标签；
- [ ] 每个 `compound_id` 可确定性复算，重跑不变且全局唯一；
- [ ] 每条来源记录都有唯一 `record_key`，可回溯至阶段 1 和原始来源；
- [ ] 所有重复组都有显式分类和解析结果；
- [ ] 所有明确标签冲突均经审核或排除，不使用静默多数投票；
- [ ] 每个 `resolved + eligible` 样本恰好属于一个主 split，其他可解析结构不被强制划分；
- [ ] train、validation、external test 无完整结构交叉；
- [ ] development 与 external test 无 connectivity 交叉；
- [ ] scaffold、近邻、activity cliff 和来源偏倚均有报告；
- [ ] 固定输入和 seed 重跑得到完全相同的文件哈希；
- [ ] external 未进入调参、特征选择、阈值、校准或模型选择；
- [ ] dry-run、批准、正式提交和独立复核链条完整；
- [ ] Manifest、报告、测试、Git 提交和 `modeling-dataset-v1` 标签齐全。

## 11. 实现前待审查事项

本稿确认后才实现组装和审计代码。首次实现不得直接生成正式数据，应先完成：

1. 固定输出 schema 和受控枚举；
2. 建立人工冲突决策空模板；
3. 实现输入指纹、dry-run 和事务提交骨架；
4. 实现来源级映射与 exact duplicate 解析；
5. 实现结构关系、相似度和泄漏审计；
6. 实现随机 split、分层 CV 和 scaffold CV；
7. 实现数据概况报告和 external 加载保护；
8. 补齐确定性、篡改拒绝、泄漏反例和端到端回归测试。

本策略审查通过前，不运行 dataset assembly dry-run，也不创建 `data/modeling/v1/` 或
`data/splits/v1/`。
