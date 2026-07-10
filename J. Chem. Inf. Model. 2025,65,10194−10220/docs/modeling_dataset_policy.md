# 建模数据集组装、泄漏审计与 split v1 策略（实现批准版）

状态：`APPROVED FOR IMPLEMENTATION`。本状态只批准 schema registry、序列化器、状态校验器和
audit dry-run 骨架的实现，不批准跳过 dry-run 或直接生成正式 release。

本文档规定阶段 2 的来源记录重建、结构实体组装、角色内标签解析、数据划分、泄漏审计和冻结规则。
本阶段不生成模型特征、不训练模型，也不修改阶段 1 已冻结的 `data/processed/`。

## 1. 冻结基线、权限与输入

阶段 2 只接受以下清洗冻结点：

- Git 标签：`dataset-cleaning-v1.2`；
- 正式清洗 run-id：`20260705_154614_567321_UTC_444f5190`；
- 批准的清洗审计 run-id：`20260705_135742_751888_UTC_444f5190`；
- 清洗输入指纹：
  `444f5190c91d070f1a9c469d1db6aef7f93ce9a2c6228f1487d021d7cc42f248`。

`data/processed/` 是只读输入。组装程序不得覆盖、修补或重新解释其中任何文件。

### 1.1 v1 的权限边界

阶段 2 v1 是重建、验证和重新打包阶段。阶段 1 的明确标签、结构排除和泄漏阻断事实均为只读；唯一批准的
成员/标签扩展是第 4 节对来源标签冲突执行的三步计数裁决。未通过前两步的 conflict、uncertain、structure
conflict 和 excluded 项继续不进入主 split。

阶段 2 会重新计算标签、结构状态和泄漏状态以验证上述结果。阶段 1 的若干派生 CSV 是互斥的
优先级视图，不是完整的正交状态表；阶段 2 可以从来源事实中显式恢复被更高优先级排除原因遮蔽的
并发原因，并只可按第 4 节对冲突产生新增的可追溯二分类成员。

冻结数据的确定性回归事实为：来源记录可重建 614 个 `compound_id × dataset_role` 明确标签冲突；
`conflict_set.csv` 是其中 `structure_status=eligible` 的 613 项精确子集。额外一项为 development 的
`VZUNGTLZRAYYDE-UHFFFAOYSA-N`，它同时属于已知 structure representation conflict，因阶段 1 先按
结构排除而未进入 conflict 视图。阶段 2 必须同时保留它的 `label_status=conflict` 和
`structure_status=ineligible`，并纳入计数裁决审计；这不视为新的阶段 1 错误。

除上述由阶段 1 优先级可完全解释的正交共存原因及第 4 节批准的自动裁决外，新的 structure-eligible
标签冲突、primary 泄漏、资格变化或无法解释的派生视图差异都会使组装失败。

### 1.2 13 张清洗表的使用方式

不得把 13 张 CSV 纵向拼接。它们包含来源事实、化合物视图、划分视图和排除视图，直接拼接会
重复计算同一证据。

- `source_records_audit.csv` 是来源级事实表，用于构建 `records_all.csv`；
- `development_pool.csv`、`external_ccris_test.csv`、`conflict_set.csv`、
  `uncertain_set.csv` 和 review candidate 表是阶段 1 的化合物级决策视图；
- `excluded_set.csv` 提供排除原因和仍需参与泄漏拦截的结构键；
- `structure_representation_conflict.csv` 提供已知结构表示异常；
- `train.csv` 和 `validation.csv` 只用于逐键核对论文复刻划分。

组装程序必须按阶段 1 的优先级语义核对派生视图与来源事实表：互斥视图可以省略被更高优先级
原因遮蔽的次级状态。阶段 1 明确标签成员的 membership 和标签必须完全一致；任何新增成员只能来自
第 4 节的第三步，且必须由冲突裁决 artifact 逐项解释。

## 2. 统一端点与来源证据

### 2.1 主任务标签

```text
1 = carcinogen
0 = noncarcinogen
```

只允许阶段 1 中 `label_category=positive/negative` 且 `label_confidence=high` 的致癌性证据产生
二分类标签。ambiguous、equivocal、inadequate、not classifiable、suggestive、probable、possible、
部分阳性、带限定语结果和非致癌性终点不得被强制映射为 0 或 1。

| 来源 | 标签 1 | 标签 0 | 非二分类 |
|---|---|---|---|
| CPDB | `+`、`c` 且试验充分 | `-` 且试验充分 | `p`、`a`、`e`、`0`、空值、`inad=i` 等 |
| IRIS | `A (Human carcinogen)`、`Carcinogenic to humans` | `E (Evidence of non-carcinogenicity for humans)` | probable、possible、likely、suggestive、D 类、证据不足、无法分类和带条件的 not likely |
| CCRIS | 致癌性结果严格等于 `POSITIVE` | 致癌性结果严格等于 `NEGATIVE` | 带限定语、非致癌性终点、方向不明或证据不足 |

映射必须从 `label_raw`、`label_category`、`label_candidate`、`label_confidence` 和 `label_reason`
重建并断言一致，不能只相信 `label_binary`。

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

每条来源记录必须命中且只命中一个规则；新值或未知值直接失败，不允许默认阴性兜底。

### 2.2 角色内独立解析

标签必须先在数据角色内解析：development 只使用 CPDB/IRIS，external 只使用 CCRIS。对同一
`compound_id × dataset_role`：

1. 只有明确阳性：`label_status=clear_positive`、`role_normalized_label=1`；
2. 只有明确阴性：`label_status=clear_negative`、`role_normalized_label=0`；
3. 明确阳性与明确阴性并存：`label_status=conflict`、标签为空；
4. 只有不确定或候选证据：`label_status=uncertain`、标签为空；
5. 明确标签与相反方向弱证据并存：保留明确标签，同时增加
   `discordant_nonclear_evidence` 审计标志。

不按物种、性别、试验次数、来源数或数据库数多数投票。弱证据不得推翻明确证据或打破明确冲突。

跨角色证据永不共同投票。同一结构可以同时具有 development=1 和 external=0；两条角色解析必须
同时保留。external 证据不得确认、改写或冲突化 development 标签。

### 2.3 证据类型

`evidence_type` 只允许：

- 所有 IRIS 致癌分类记录：`human_weight_of_evidence`；
- 有明确实验动物物种的 CPDB/CCRIS：`animal_experimental`；
- 物种无法可靠判定的 CPDB/CCRIS：`experimental_unspecified`。

标签资格只由 `label_rule` 决定。每条 `records_all.csv` 记录必须恰好有一个合法、非空
`evidence_type`。来源、证据类型、物种或来源 ID 不得成为正式结构模型特征。

## 3. 三层数据模型

### 3.1 来源记录：`records_all.csv`

每行对应 `source_records_audit.csv` 的一条来源记录。必须无损保留其全部原列、原始文本和 JSON
字段，再新增：

```text
record_key
source_dataset
source_label
normalized_label
label_rule
evidence_type
cleaning_run_id
```

若计划派生的字段名已经存在于来源事实表，程序必须重算并逐行断言与冻结值一致，然后复用原列，
不得创建同名重复列；只有来源表不存在的字段才允许新增。任何值、dtype 语义或缺失模式不一致都
直接失败。输出前再次断言列名全局唯一。

来源到角色映射固定为：

```text
cpdb  → development
iris  → development
ccris → external
```

来源事实表已有 `dataset_role` 时，必须逐行与该映射完全一致。

不得删除或摘要化 `source_payload_json`、`structure_provenance`、`raw_smiles`、
`leakage_connectivity_keys_json` 和人工无机碳审核字段。

#### record key 预检查

执行前必须断言：

- `source_dataset` 和 `source_record_id` 非空；
- `source_dataset` 属于固定枚举 `cpdb/iris/ccris`；
- `source_record_id` 在同一 `source_dataset` 内唯一；
- 不使用 DataFrame 行号或文件行号兜底。

`source_record_id` 必须从 CSV 按原始字符串读取，禁止数值类型推断、`.strip()`、大小写转换或
Unicode 规范化；前导零和全部原字符必须保留。canonical JSON 哈希使用的仍是该原始字符串，
因此 `"00123"` 与 `"123"` 是不同 ID。

冻结数据的 `source_record_id` 可以包含冒号，因此不使用未转义字符串拼接。`record_key` 固定为：

```text
REC:<sha256(canonical_json([source_dataset, source_record_id]))>
```

其中 canonical JSON 使用第 10 节规范。生成后再次断言全局唯一。

### 3.2 结构实体：`compounds.csv`

只要来源记录具有有效 `standardized_inchikey`，就形成一个结构实体：

```text
compound_id = CMP:<standardized_inchikey>
```

`compounds.csv` 一结构一行，只保存结构身份、结构表示和来源追溯，不保存角色标签或 split 资格。
至少包含：

```text
compound_id
standardized_inchikey
connectivity_key
canonical_smiles
parent_smiles
source_canonical_smiles_json
parent_smiles_variants_json
nonisomeric_parent_smiles
tautomer_family_key
murcko_scaffold
structure_status
structure_reasons_json
source_record_keys_json
cleaning_run_id
```

阶段 1 到阶段 2 的字段映射固定为：

```text
stage1 standard_inchikey → stage2 standardized_inchikey
stage1 canonical_smiles  → stage2 source_canonical_smiles_json 的成员
stage1 parent_smiles     → stage2 parent_smiles_variants_json 的成员
stage1 connectivity_key  → stage2 connectivity_key 的核对来源
```

`standardized_inchikey` 必须匹配 `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`。唯一 parent 解析为 `parent_mol`
后，完整键固定使用 `rdkit.Chem.inchi.MolToInchiKey(parent_mol)` 重算，并必须等于冻结
`standardized_inchikey`。`connectivity_key` 固定为 `standardized_inchikey.split("-")[0]`；同一
compound 的所有非空阶段 1 connectivity key 必须都等于该 14 字符值。格式、重算键或任一来源键
不一致均直接失败。

无有效标准键的记录不能伪造 `compound_id`，只进入 `records_all.csv`、`record_exclusions.csv` 和统计。

#### 结构代表字段

1. `source_canonical_smiles_json` 保留全部非空来源 canonical SMILES；
2. `parent_smiles_variants_json` 保留全部非空 parent SMILES；
3. parent 变体恰好一个时，`parent_smiles` 取该值，`canonical_smiles` 由该 parent 重新解析后使用
   `MolToSmiles(canonical=True, isomericSmiles=True)` 生成；
4. parent 变体多于一个时，必须与冻结的 `structure_representation_conflict.csv` 中同一 InChIKey
   的变体集合完全一致。已知 4 个键设置 `structure_status=ineligible`，所有单值代表结构和派生结构
   字段留空，全部变体仍由 JSON 保存；
5. 新的多 parent 键、已声明键缺失、额外声明或变体集合不一致都会使组装失败；
6. 来源 canonical 多值但 parent 唯一不构成结构冲突，不得任取来源首行作为代表。

`structure_status` 在 compound 层只允许 `eligible` 或 `ineligible`。无标准键的 record-level 状态为
`no_standardized_key`，不进入 compound 层。

#### 结构状态判定顺序

阶段 2 必须区分“合法承接阶段 1 排除”和“冻结输入异常”。对每个具有有效标准键的 compound，按
以下顺序判定，同时把所有适用的非致命原因写入 `structure_reasons_json`：

| 顺序与条件 | 处理 | reason |
|---|---|---|
| 标准键格式非法 | 直接失败 | `invalid_frozen_standardized_key` |
| parent 变体多于一个但不与冻结结构冲突表精确一致 | 直接失败 | `undeclared_structure_representation_conflict` |
| parent 变体多于一个且与冻结结构冲突表精确一致 | `ineligible` | `structure_representation_conflict` |
| 没有非空 parent，且任一来源记录声称 `model_structure_ok=true` | 直接失败 | `modelable_record_missing_parent` |
| 没有非空 parent，且全部来源记录不可建模 | `ineligible` | `missing_parent_smiles` |
| 唯一 parent 在锁定环境中无法解析 | 直接失败 | `frozen_parent_parse_failure` |
| 唯一 parent 重算 standard InChIKey 与冻结键不一致 | 直接失败 | `standardized_key_mismatch` |
| 所有来源记录均为 `model_structure_ok=false` | `ineligible` | `no_modelable_source_record` |
| 至少一条来源记录 `model_structure_ok=true`，且以上异常均不存在 | `eligible` | 无强制排除原因 |

同一 compound 既有可建模记录又有其他 record-level 排除时，compound 可以保持 `eligible`，但被排除
记录及原因必须留在 `record_exclusions.csv`；不能因任一来源行被排除就排除整个结构。

只有初步判为 `eligible` 的 compound 才要求全部关键派生算法成功，包括 canonical representative、
non-isomeric parent、tautomer family、Murcko scaffold 和 ECFP4。任一失败都会使整个组装失败，因为
阶段 2 无权通过新排除改变冻结 membership。已为 `ineligible` 的 compound 可以不计算不适用的派生
字段并写空，但不得隐藏其阶段 1 原因。

### 3.3 角色解析：`compound_role_resolutions.csv`

每行对应一个 `compound_id × dataset_role`。至少包含：

```text
compound_id
dataset_role
role_normalized_label
label_status
review_status
label_resolution_record_keys_json
nonresolution_record_keys_json
label_resolution_sources_json
discordant_nonclear_count
has_discordant_nonclear_evidence
structure_status
leakage_status
has_tautomer_overlap
split_eligibility
exclusion_reasons_json
resolution_rules_json
cleaning_run_id
```

同一结构跨角色时保留两行。例如 development 可以 `eligible`，external 同时因
`exact_overlap` 为 `ineligible_leakage`。不得使用单一 `primary_role` 或单一全局标签覆盖角色状态。

对每个 compound-role，来源记录集合必须满足：

```text
label_resolution_record_keys ∩ nonresolution_record_keys = ∅
label_resolution_record_keys ∪ nonresolution_record_keys
  = 该 compound_id × dataset_role 的全部 record_key
```

`label_resolution_record_keys_json` 只能包含实际参与角色标签解析的明确二分类记录；弱证据、
非致癌性终点、相反方向 nonclear 证据和其他非明确记录必须进入
`nonresolution_record_keys_json`。其他角色的记录不属于当前 role 的全集，不能混入任一集合。
`label_resolution_sources_json` 只能从 resolution keys 对应记录派生。每个 key 必须存在于
`records_all.csv`，且其 compound ID 和 dataset role 与当前行完全匹配；漏记、重复归属或交叉归属
都会使组装失败。

只有 `label_candidate` 明确具有 positive/negative 方向、当前角色已经获得唯一 clear binary 标签，
且 candidate 方向与该 clear 标签相反时，才计入 `discordant_nonclear_count`。对于
`label_status=conflict/uncertain`，该计数固定为 0，布尔字段固定为 `false`；其他情况下
`has_discordant_nonclear_evidence = (discordant_nonclear_count > 0)`。角色表的计数和布尔值必须与
`duplicate_groups.csv` 同一 compound-role 的值完全一致，否则失败。

### 3.4 三个独立状态轴

`label_status`：

```text
clear_positive
clear_negative
conflict
uncertain
```

`structure_status`：

```text
eligible
ineligible
```

`no_standardized_key` 只用于 record-level exclusion，不会出现在角色解析表。

`leakage_status`：

```text
not_applicable
clear
exact_overlap
connectivity_overlap
```

development 固定为 `not_applicable`。external 按严重程度
`exact_overlap > connectivity_overlap > clear` 取一个值。

`has_tautomer_overlap` 是独立布尔字段，只允许 `true/false`。它不参与 primary 资格，仅决定跨角色
tautomer 报告和 sensitivity external。因而
`leakage_status=exact_overlap, has_tautomer_overlap=true` 是合法且信息完整的组合。
development 行固定为 `false`；external 行在其非空 tautomer family 与第 7.3 节 development 比较全集
有交集时为 `true`，否则为 `false`。

`review_status`：

```text
not_required
pending
confirmed_exclude
```

#### 合法组合与资格派生

| 条件（按顺序） | `split_eligibility` | 必须加入的排除原因 |
|---|---|---|
| `structure_status=ineligible` | `ineligible_structure` | 全部结构原因 |
| 否则 `label_status in {conflict, uncertain}` | `ineligible_label` | `label_conflict` 或 `label_uncertain` |
| 否则 external 且 `leakage_status=exact_overlap` | `ineligible_leakage` | `external_exact_overlap` |
| 否则 external 且 `leakage_status=connectivity_overlap` | `ineligible_leakage` | `external_connectivity_overlap` |
| 否则标签明确、结构合格且 leakage 为 `not_applicable/clear` | `eligible` | 无 primary 排除原因 |

附加合法性约束：

- `clear_positive` 必须对应标签 1，`clear_negative` 必须对应标签 0；
- `conflict/uncertain` 的标签必须为空；
- `conflict` 在 audit 可为 `pending/confirmed_exclude`，正式 release 只能为
  `confirmed_exclude`；
- 非 conflict 必须为 `not_required`；
- development 的 leakage 只能为 `not_applicable`；external 不得为 `not_applicable`；
- `has_tautomer_overlap` 可与任何 leakage 状态共存，不得从 exact/connectivity 状态反向推断；
- `exclusion_reasons_json` 保留所有同时成立的标签、结构、泄漏原因，不因资格优先级丢失信息；
- 表驱动校验所有组合，未知枚举或非法组合直接失败。

`resolution_rules_json` 中的规则枚举至少覆盖：

```text
unanimous_clear_positive
unanimous_clear_negative
confirmed_exact_label_conflict_exclude
no_clear_binary_label
structure_ineligible
external_exact_leakage
external_connectivity_leakage
external_tautomer_overlap_reported
```

一个角色行可以有多个规则，固定为去重、排序 JSON 数组；不得用单一规则覆盖其他维度。

### 3.5 排除表

`compound_exclusions.csv` 一行对应一个 compound-role-reason，包含标签、结构、泄漏等全部
compound-level 排除，不只保存冲突。唯一键为
`compound_id, dataset_role, exclusion_reason`。

`record_exclusions.csv` 一行对应一个 `record_key × exclusion_reason`，唯一键就是这两列；至少包含
`record_key, source_dataset, source_record_id, exclusion_reason`。它必须覆盖：

- 无标准键记录；
- 每条 `model_structure_ok=false` 来源记录的全部阶段 1 原因；
- 其他来源级排除原因；
- 所属 compound 最终因其他来源记录可建模而 `structure_status=eligible` 的被排除记录。

同一记录有多个原因时分别保存多行，禁止重复 reason 行。`model_structure_ok=false` 却没有可映射
来源级原因时直接失败，不生成含糊的默认原因。

强制断言：从 `records_all.csv` 按 schema registry 规则展开得到的全部
`record_key × exclusion_reason` 集合，与 `record_exclusions.csv` 的集合完全相等。

`structure_reasons_json` 只保存 compound-level 原因，例如已知表示冲突、缺失 parent 或
`no_modelable_source_record`；单条来源记录的具体排除原因只进入 `record_exclusions.csv`。不得因
同结构的其他记录可建模而丢失 record reason，也不得把单条 record reason 错误提升为整个 compound
的排除原因。

专项 `label_conflicts.csv` 是 `compound_exclusions.csv` 和角色解析表的报告视图，不能代替完整排除表。

## 4. 标签冲突计数裁决

阶段 1 来源事实中重建出的 614 个确定性 compound-role 标签冲突（包括被结构优先排除遮蔽的
`VZUNGTLZRAYYDE-UHFFFAOYSA-N × development`）不再逐条人工投票，而是按以下固定、顺序敏感的
三步规则自动裁决。所有比较均只使用 `clear_positive_count` 和 `clear_negative_count`，不将
`nonbinary_count` 计入阈值。

1. 若 `clear_positive_count + clear_negative_count <= 10`，排除；
2. 否则，若 `abs(clear_positive_count - clear_negative_count) <= 10`，排除；
3. 否则，记录数较多的一方为最终标签：阳性更多则标记 `1/clear_positive`，阴性更多则标记
   `0/clear_negative`。

规则按上述顺序执行：第一步命中时，不再计算第二步；第三步仅在前两步均未命中时执行。因此不存在
平局被标记为二分类标签的情况。按当前冻结输入，614 个来源冲突中 451 个因总数不超过 10 排除，87 个因
差值绝对值不超过 10 排除，51 个自动标为阳性，25 个自动标为阴性。

自动裁决必须保留完整审计证据。`modeling/conflict_reviews.csv` 是正式 artifact，字段为：

```text
compound_id,dataset_role,clear_positive_count,clear_negative_count,
decision,resolved_label,resolution_reason
```

`decision` 只允许 `exclude_total_count_le_10`、`exclude_count_margin_le_10`、`assign_positive` 或
`assign_negative`。前两种决策的 `resolved_label` 为空；后两种分别只能为 `1` 和 `0`。
`reports/label_conflicts.csv` 为同一裁决的报告视图。`reports/modeling_conflict_review_candidates.csv`
是 audit-only 归档，额外保留来源记录键和最终 `review_status`；它不进入 formal release artifact
集合，但必须由 audit manifest 完整保护。

## 5. 重复组与结构关系

### 5.1 来源记录重复组

exact duplicate 是同一 compound 内部来源记录的聚合结果，不是两个 compound 间的边。
`duplicate_groups.csv` 一行对应 `compound_id × dataset_role`，至少包含：

```text
compound_id
dataset_role
record_count
record_keys_json
source_labels_json
clear_positive_count
clear_negative_count
nonbinary_count
discordant_nonclear_count
has_discordant_nonclear_evidence
exact_duplicate_class
```

`exact_duplicate_class` 只允许：

```text
single_record
multiple_clear_same_label
multiple_clear_with_nonbinary
multiple_clear_conflicting
multiple_nonbinary_only
```

计数按该 compound-role 的全部来源记录计算，`nonbinary_count` 包含未参与明确二分类解析的记录；
`discordant_nonclear_count` 是其中方向与最终明确标签相反的 nonclear 记录数。主分类按以下顺序穷尽
派生：

1. `record_count == 1` → `single_record`；
2. `clear_positive_count > 0 AND clear_negative_count > 0` →
   `multiple_clear_conflicting`；
3. 明确标签只有一侧且 `nonbinary_count > 0` → `multiple_clear_with_nonbinary`；
4. 明确标签只有一侧且 `nonbinary_count == 0` → `multiple_clear_same_label`；
5. 两侧明确标签计数均为 0 → `multiple_nonbinary_only`。

`has_discordant_nonclear_evidence = (discordant_nonclear_count > 0)`，作为与主分类正交的审计字段。
所有计数必须为非负整数，且
`clear_positive_count + clear_negative_count + nonbinary_count = record_count`、
`discordant_nonclear_count <= nonbinary_count`。

### 5.2 结构关系边

`structure_relation_edges.csv` 只允许 `compound_id_a != compound_id_b`。每行是一条结构关系在一个
标签比较 scope 下的结果，至少包含：

```text
comparison_scope
compound_id_a
dataset_role_a
compound_id_b
dataset_role_b
relation_type
similarity
label_a
label_b
label_relation
```

`comparison_scope` 为 `development/external/cross_role`。无序结构 ID 始终按 Unicode 字典序满足
`compound_id_a < compound_id_b`，角色字段保留实际比较方向。

`relation_type` 只允许：

```text
same_connectivity
stereo_variant
tautomer_related
high_similarity
```

同一 pair 可有多种 relation，每种各一行；唯一键为
`comparison_scope, compound_id_a, dataset_role_a, compound_id_b, dataset_role_b, relation_type`。

每种 edge 的触发条件固定如下：

- `same_connectivity`：两端 compound ID 不同、两端 `connectivity_key` 均非空且完全相同；
- `stereo_variant`：满足 `same_connectivity`，两端完整 InChIKey 不同，并且非空
  `nonisomeric_parent_smiles` 完全相同；满足时同时输出 `same_connectivity` 和
  `stereo_variant` 两条 edge；
- `tautomer_related`：两端 compound ID 不同、非空 `tautomer_family_key` 完全相同；无论是否还
  满足 connectivity 条件，都单独输出该 edge；
- `high_similarity`：两端 compound ID 不同且固定 ECFP4 Tanimoto ≥0.85；无论是否满足其他关系，
  都单独输出该 edge。

`similarity` 只在 `high_similarity` edge 中写入固定序列化的有限浮点值，其他 relation 留空。

`label_relation` 独立取 `same/opposite/not_comparable`。任一端没有明确角色标签时为
`not_comparable`。`label_discordant_near_neighbors.csv` 只从
`relation_type=high_similarity AND label_relation=opposite` 派生，并在说明中保留
“activity-cliff candidate”作为论文对照术语。

`cross_role` scope 对每个存在的 development role row 与 external role row 组合分别生成：对于无序
compound pair A/B，若组合存在，则同时独立考虑 `A(development)↔B(external)` 和
`A(external)↔B(development)`，最多两条 role 组合 edge。按 compound ID 排序后，
`dataset_role_a/b` 始终随各自 compound 保持，不因排序交换证据语义；不得任意只保留一个方向。

比较宇宙为 `compounds.csv` 中结构合格且 parent 可解析的 compound；角色 scope 由角色解析表决定。
exact cross-role overlap 是同一 compound 的两个角色行，不进入 pair 表，记录在角色解析和泄漏报告。

### 5.3 结构算法

`nonisomeric_parent_smiles`：从标准化 parent 清除原子手性、双键立体和同位素编号后，使用
`MolToSmiles(canonical=True, isomericSmiles=False)`。

`tautomer_family_key`：对上述分子使用 RDKit `TautomerEnumerator`，显式设置
`SetRemoveSp3Stereo(False)`、`SetReassignStereo(True)`，其余参数保持锁定版本默认值；canonical
tautomer 转为 canonical non-isomeric SMILES 后，定义为
`TAU:<完整 SHA-256(UTF-8 SMILES)>`。失败时显式报告，不允许名称兜底。

ECFP4 固定为 `GetMorganFingerprintAsBitVect`：`radius=2`、`nBits=2048`、
`useChirality=True`、`useBondTypes=True`、`useFeatures=False`、
`includeRedundantEnvironments=False`；输入为标准化 `parent_smiles`。Tanimoto 使用
`DataStructs.TanimotoSimilarity`，阈值为 0.85。

所有参数、RDKit 版本和实现签名进入输入指纹。

## 6. Scheme C 与 split v1

### 6.1 Primary 80:20 holdout

主划分采用论文对照的固定随机协议：

```text
sklearn.model_selection.train_test_split
test_size = 0.20
random_state = 42
stratify = normalized_label
shuffle = True
```

输入为通过结构、标签和泄漏资格校验的 development 候选，按 `standardized_inchikey` 升序。阶段 1
`development_pool.csv` 中的明确标签成员必须完整保留并保持标签；按第 4 节第三步新增的成员参与同一
固定随机划分，因此 train/validation 不再要求逐键复现阶段 1 的旧划分。

### 6.2 三种独立 CV 协议

以下协议相互独立，不得混用其结果：

1. `full_development_stratified_cv_folds.csv`：完整 development 的分层 5 折，用于复现论文的独立
   CV 评估；
2. `full_development_scaffold_cv_folds.csv`：完整 development 的 scaffold-grouped 5 折，用于独立
   稳健性评估；
3. `train_tuning_cv_folds.csv`：只覆盖固定 train 的分层 5 折，供后续超参数选择使用，不包含固定
   validation。

前两种 full-development CV 不得用于调参后再把固定 validation 描述为未参与选择的独立验证集。
scaffold CV 也不得含糊地兼任 primary holdout 的调参工具。

分层 CV 固定使用 `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`。输入分别使用完整
development 或固定 train 的标准 InChIKey 升序；fold 编号为 0–4。输出每个输入 compound 恰好一行：

```text
compound_id,standardized_inchikey,normalized_label,fold_id
```

调用两套 StratifiedKFold 前，分别断言其输入 `positive_count >= 5` 且 `negative_count >= 5`；生成后
断言每个 fold 都非空且同时包含两个类别。禁止依赖 scikit-learn warning 后继续生成退化 fold。

### 6.3 Scaffold CV 的确定分组

Murcko scaffold 固定生成算法：解析标准化 parent，调用
`MurckoScaffold.GetScaffoldForMol`，调用 `Chem.RemoveStereochemistry`，再使用
`MolToSmiles(canonical=True, isomericSmiles=False)`。无原子 scaffold 定义为空字符串。重算值必须
与阶段 1 `murcko_scaffold` 一致，否则失败。

每个 eligible compound 的 `connectivity_key` 必须非空。基础组键：非空 scaffold 使用
`SCAFFOLD:<smiles>`，空 scaffold 使用 `ACYCLIC:<connectivity_key>`。共享非空 scaffold 或共享
connectivity key 的 compound 连边；每个连通分量是最终 group，`group_key` 是分量中 Unicode
字典序最小的 `compound_id`。

确定性分配：

1. group 按样本数降序、阳性数降序、group key 升序；
2. 对每个候选 fold 计算加入该 group 后的全局分数：
   `Σ_f[((n_f-N/5)/N)^2 + ((p_f-P/5)/P)^2 + ((q_f-Q/5)/Q)^2]`；
3. `N/P/Q` 和所有 `n/p/q` 是整数，要求 `P>0`、`Q>0`；使用 `fractions.Fraction` 精确计算和比较，
   禁止浮点近似；
4. 分数相同时选 fold 编号最小者；
5. 每个 fold 必须包含两个类别，否则失败。

scaffold fold 输出 schema：

```text
compound_id,standardized_inchikey,normalized_label,murcko_scaffold,group_key,fold_id
```

## 7. External 隔离与敏感性集

### 7.1 Development 阻断集合

为避免“有效模型结构”的边界歧义，固定两个集合：

```text
development_exact_block_set =
  所有具有 development 角色且 standardized_inchikey 非空的 compound 的完整键
```

该集合不受 `label_status`、`review_status`、`structure_status` 或 `split_eligibility` 影响。

```text
development_connectivity_block_set =
  所有具有 development 角色且 connectivity_key 非空的 compound 的连接键
  ∪ excluded_set.csv 中 dataset_role=development 记录的全部
    leakage_connectivity_keys_json 非空成员
```

两个集合都绝不加入 external-only 的 excluded 或 leakage key。不得通过删除 development 项扩大
external。集合成员、来源类型和贡献 record/compound 必须写入泄漏审计报告。

### 7.2 Primary external

primary external 保留阶段 1 `external_ccris_test.csv` 的所有合格明确标签成员和标签，并可纳入第 4 节
第三步新增、且通过泄漏拦截的 external 成员。强制断言：

```text
primary_external standardized_inchikey ∩ development_exact_block_set = 0
primary_external connectivity_key ∩ development_connectivity_block_set = 0
train ∩ validation exact InChIKey = 0
train ∩ primary_external exact InChIKey = 0
validation ∩ primary_external exact InChIKey = 0
```

### 7.3 Tautomer 敏感性集

跨角色 `tautomer_family_key` overlap 不改变 primary external membership，只强制报告到
`cross_role_tautomer_overlaps.csv`。另生成：

```text
external_test_tautomer_clean_sensitivity.csv
```

tautomer 比较全集是所有具有 development 角色、`structure_status=eligible` 且 tautomer key 非空的
compound，不论其 development 标签是明确、冲突还是 uncertain。该敏感性集从 primary external 中
删除与比较全集任一结构共享 tautomer family 的项；每个删除都保留原因和对应 development
compound。敏感性集不得用于调参或替代 primary external 主结论。

`cross_role_tautomer_overlaps.csv` 一行对应一个 external compound，至少包含：

```text
external_compound_id
tautomer_family_key
development_compound_ids_json
in_primary_external
removed_from_tautomer_sensitivity
```

`development_compound_ids_json` 保存比较全集中全部匹配 development compound，去重排序且不得只留
任意一个代表。两个布尔字段必须与 primary 和 sensitivity split membership 逐键一致。

### 7.4 相似度与最近邻审计

必须报告：

- train/validation/external 的 Murcko scaffold 重叠率；
- 每个 external 到 train 的最大 ECFP4 Tanimoto；
- Tanimoto ≥0.85 的近邻 pair；
- `label_discordant_near_neighbors.csv`；
- train/validation connectivity overlap；
- external 各来源、证据类型和类别分布。

对 validation、primary external 和 sensitivity external 相对 train 的 scaffold overlap 同时报告：

- compound-weighted rate：目标集中 scaffold 在 train 出现的 compound 数 / 目标集 compound 总数；
- scaffold-weighted rate：目标集中也在 train 出现的唯一非空 scaffold 数 / 目标集唯一非空 scaffold
  总数。

分母为 0 时 rate 留空并记录 `no_scaffolds`，不得把两种口径混称为一个“scaffold overlap rate”。

`nearest_neighbors.csv` 至少包含：

```text
query_compound_id
query_split
nearest_compound_id
nearest_split
similarity
query_label
nearest_label
label_relation
```

train 查询必须排除自身；没有其他 train compound 时相似度为空。所有并列最近邻按 compound ID
选择字典序最小者，同时在高相似 pair 报告中保留全部并列关系。

查询全集固定为：

```text
train → train
validation → train
external_test → train
external_tautomer_sensitivity → train
```

同一 compound 同时属于 primary external 和 sensitivity external 时，在两个 `query_split` 下各输出
一行，以便两个评估集独立审计。`query_split` 固定排序为
`train, validation, external_test, external_tautomer_sensitivity`。若候选 train 为空，则
`nearest_compound_id/nearest_split/similarity/nearest_label/label_relation` 全部写空。

### 7.5 External 不可用于调参

普通训练加载器默认不得读取 external。只有显式 `evaluation_mode="external_final"` 且提供冻结
manifest 才能加载 primary external。单元测试必须验证特征选择、超参数搜索、阈值、早停、校准和
模型选择路径不接收 primary 或敏感性 external。

模型定型前不得输出 external 性能。每次最终评估记录模型工件、split manifest 哈希和时间，防止
反复查看后人工调参。

## 8. 数据概况和统计定义

对 train、validation、primary external 和 tautomer-clean sensitivity external 报告：样本数和类别
比例、来源/证据类型组成、分子量、Crippen LogP、TPSA、HBD/HBA、可旋转键、总环数、芳香环数、
重原子数、Murcko scaffold 数和单例比例、到 train 最大 ECFP4 相似度及计算失败数。

描述符输入统一为标准化 `parent_smiles`，固定调用：

| 描述符 | RDKit 实现 |
|---|---|
| 分子量 | `Descriptors.MolWt(mol)` |
| Crippen LogP | `Crippen.MolLogP(mol)` |
| TPSA | `rdMolDescriptors.CalcTPSA(mol)` |
| HBD | `rdMolDescriptors.CalcNumHBD(mol)` |
| HBA | `rdMolDescriptors.CalcNumHBA(mol)` |
| 可旋转键 | `rdMolDescriptors.CalcNumRotatableBonds(mol, strict=True)` |
| 总环数 | `rdMolDescriptors.CalcNumRings(mol)` |
| 芳香环数 | `rdMolDescriptors.CalcNumAromaticRings(mol)` |
| 重原子数 | `mol.GetNumHeavyAtoms()` |

解析或计算失败必须按 compound、split 和描述符记录，不能用 0 填充。函数、参数和 RDKit 版本进入
输入指纹。

对应确定性报告固定为 `descriptor_failures.csv`，字段为
`compound_id,query_split,descriptor,error_reason`。`scaffold_summary.csv` 同时记录
`singleton_scaffold_count` 和 `singleton_scaffold_rate`；`similarity_summary.csv` 同时记录有效
`count` 和缺失 `missing`。

### 8.1 描述统计

- `std` 和方差使用总体定义 `ddof=0`；
- 分位数为 P05/P25/P50/P75/P95，使用 NumPy `method="linear"`；
- 连续变量输出 count、missing、mean、std、min、P05、P25、median、P75、P95、max；
- 浮点缺失按第 10 节写为空字符串，不输出 NaN/Infinity。

每个 summary 行增加 `summary_status`。有效观测 `count=0` 时，mean/std/min/全部分位数/max 均为空，
状态为 `no_observations`，不得调用 NumPy 聚合；`count=1` 时 std=0、全部分位数等于唯一观测，状态
为 `ok`；`count>=2` 按上述参数计算并记 `ok`。数据集为空或某描述符全部失败都是合法的可报告
状态，不能依赖底层库异常决定输出。

### 8.2 分布漂移

validation 与 train、external 与 train 分别计算：

```text
SMD = (mean_comparison - mean_train) / sqrt((var_train + var_comparison) / 2)
```

方差使用 `ddof=0`。分母为零且均值相同则 SMD=0；分母为零且均值不同则 SMD 留空，并记录
`smd_status=undefined_zero_variance`。

双样本 KS 固定为 `scipy.stats.ks_2samp(alternative="two-sided", method="exact")`。

若 comparison 或 train 的有效观测集合任一为空，SMD、KS statistic 和 KS p-value 全部留空，统一
`test_status=insufficient_observations`，且不得调用 SciPy。其他情况下按定义计算；SMD 的零方差状态
另由 `smd_status` 保存。

来源组合与标签的列联表先删除边际和为零的行列，再使用
`scipy.stats.chi2_contingency(correction=False)`；记录有效行列数。Cramér's V 使用未校正公式
`sqrt(chi2 / (n * min(r-1,c-1)))`，分母为零时记 0。

当总样本 `n=0`、有效行数小于 2 或有效列数小于 2 时，不调用 `chi2_contingency`，Cramér's V
固定为 0，卡方 statistic/p-value 留空，`test_status=degenerate_table`；否则状态为 `ok`。

来源组合只从 `label_resolution_sources_json` 生成，不把跨角色或弱证据混入。任一来源组合样本数
不少于 20 且纯度 `max(positive_rate, 1-positive_rate) >= 0.90`，或 Cramér's V ≥0.30 时，manifest
标记 `source_label_confounding_warning=true`，但不改变标签和 split。
列联检验结果同时写入 `source_label_association.csv`，字段为
`split,chi2_statistic,chi2_pvalue,cramers_v,effective_rows,effective_columns,test_status,source_label_confounding_warning`。
证据类型组成从每个样本的 `label_resolution_record_keys_json` 回溯 `records_all.evidence_type`，
去重排序后作为样本级组合，写入 `evidence_type_crosstab.csv`，字段为
`split,evidence_type_combination,label,count`。

SciPy、NumPy 和所有统计参数进入 runtime signature、输入指纹和测试。

## 9. 单一 release 事务与审计

### 9.1 目录和真相源

dry-run：

```text
audits/dataset_assembly/<audit-run-id>/
├── modeling/
├── splits/
├── reports/
├── audit_manifest.json
└── audit.log
```

正式 release：

```text
releases/dataset_assembly/<formal-run-id>/
├── modeling/
├── splits/
├── reports/
├── manifest.json
└── formal.log

releases/dataset_assembly/current_release.json
```

release 目录是唯一事务真相源。旧的 `data/modeling/v1/`、`data/splits/v1/` 和
`reports/dataset_assembly/current/` 只能是由 current pointer 派生的只读便利链接或便利副本，不能
用于审批、哈希核验或训练加载，也不能成为正式提交的事务组成部分。正式加载器必须解析
`current_release.json` 并验证 manifest。

每次加载至少执行：验证 pointer schema 和其中记录的 manifest SHA-256；验证 manifest schema、
release ID 和相对路径；验证即将读取 artifact 的实际 SHA-256、字节数、schema 和列顺序。正式训练
启动前默认验证 manifest 登记的整个 release 文件集合，拒绝缺失、额外或被篡改文件。不得只验证
manifest 后直接信任目标 CSV。

pointer 和 manifest 中的路径必须是规范化相对路径；拒绝绝对路径、空路径段、`.`、`..`，并在解析
后确认目标仍位于声明的 release 根内。正式 reader 拒绝 manifest、artifact 或其中任何父路径为
符号链接，防止路径逃逸或发布后换靶。

### 9.2 原子提交协议

1. 在与 release 根同一文件系统的临时目录完整生成 modeling、splits、reports；
2. 校验 schema、文件集合、哈希、字节数和行数；
3. 写完并关闭日志，`flush + fsync`，此后禁止追加；
4. 生成 manifest；manifest 记录日志哈希，但不记录自身哈希；写完后 `flush + fsync`；
5. `fsync` 所有子目录和临时 release 根；
6. 将完整临时根原子 rename 为唯一 `<formal-run-id>`；目标已存在则失败；
7. 生成小型临时 pointer，包含 release ID、相对路径和 manifest SHA-256；`flush + fsync` 后原子
   `os.replace` 为 `current_release.json`，再 fsync 父目录；
8. current pointer 不进入确定性 artifacts 哈希；便利链接/副本在 pointer 切换后派生，失败不影响
   release 有效性。

任何 reader 只会看到旧 pointer 或新 pointer，不会看到三个目录的新旧混合状态。

### 9.3 Dry-run 与正式比较

确定性 artifacts 是 modeling、splits 和 reports 中登记的 CSV/JSON；run-specific envelope 是
manifest、日志和 current pointer。

audit manifest 必须使用两个互斥 map：

```text
release_artifacts
audit_only_artifacts
```

`release_artifacts` 是批准后正式 release 必须重建的确定性文件；`audit_only_artifacts` 只属于审计，
当前仅含已登记的人工候选等审查辅助文件。两个 map 的路径不得重复。

正式运行必须：

- 先按 audit manifest 验证审计目录文件集合、artifact 哈希/行数和已关闭日志哈希；
- 验证当前输入指纹、环境和参数与 audit 一致；
- 重新生成 `release_artifacts` map 中全部确定性 artifacts，与批准 audit 逐文件比较集合、SHA-256、
  字节数和行数；
- 正式 manifest 中的 input fingerprint、runtime signature、settings 和 artifact maps 与 audit 一致；
- manifest/log 因 run-id、run type、审批关系和时间不同，不要求与 dry-run 同哈希。

其中正式 release 的确定性 artifact 集合必须精确等于 `audit_manifest.release_artifacts`；
manifest 和 formal log 属于另外校验的 run-specific envelope，不参与该集合等式。正式运行只重建和
比较 release map。`audit_manifest.audit_only_artifacts` 只验证其在批准 audit 中集合完整、哈希/
字节数/行数正确且未被篡改，不要求在 formal release 中重新生成或出现。

同一输入重跑时，所有确定性 artifacts 必须字节相同；run-specific envelope 可以不同。

dry-run 也采用明确的封口顺序：全部确定性 artifacts 写完并校验后，先写完、关闭和 fsync
`audit.log`，此后禁止追加；再生成记录日志哈希的 `audit_manifest.json`，manifest 不记录自身哈希；
最后 fsync 审计目录。已存在的 audit run-id 目录不得覆盖或追加。

### 9.4 Manifest 和输入指纹

输入指纹至少覆盖：

- `dataset-cleaning-v1.2` commit、正式 cleaning manifest 和 13 个 processed CSV 的哈希/行数；
- 本策略、组装模块、入口脚本、schema registry 和全部相关测试；
- 标签冲突计数裁决规则及其实现；
- 标签、结构、相似度、scaffold、split、统计和序列化参数；
- Python、平台、架构、RDKit/InChI、NumPy、pandas、scikit-learn、SciPy 及实现签名；
- 随机种子、线程和并行设置。

manifest 至少记录 schema version、run-id/type、批准 audit、输入指纹、环境、settings、输入/输出/
报告的 SHA-256/字节数/CSV 数据行数、各状态计数、自动裁决计数、split 分布和 external lock。

manifest 不记录自身哈希。审计目录、release 和 manifest 不得出现用户主目录绝对路径或凭据。

## 10. 字节级序列化规范

所有确定性 artifact 统一使用：

### 10.1 CSV

- UTF-8，无 BOM；换行符只允许 LF；文件以一个 LF 结束；
- 分隔符 `,`，quotechar `"`，`doublequote=True`，`quoting=csv.QUOTE_MINIMAL`；
- 列顺序来自版本化 schema registry，缺列、多列和重复列均失败；
- 行顺序使用第 10.3 节排序键；排序稳定且使用 Unicode code point 顺序；
- 缺失值统一为空字符串；字符串不做 locale 变换；
- 布尔值固定为小写 `true/false`；整数使用十进制且无千位符；
- 有限浮点统一使用 Python `format(value, ".17g")`；`-0` 和 `-0.0` 规范为 `0`；
- NaN 和正负 Infinity 禁止；按业务规则允许缺失时写空字符串；
- 输入字段出现 `\r` 直接失败；字段内部允许原始 `\n`，必须由 CSV 引号正确包裹，不 trim、不替换；
- CSV 行数是使用上述锁定 dialect 解析得到的逻辑数据记录数，不是 LF 物理行数，且不含表头。

### 10.2 JSON 与时间

- JSON 编码 UTF-8、无 BOM，`sort_keys=True`、`ensure_ascii=False`、
  `separators=(",", ":")`、`allow_nan=False`；
- JSON 数组先按字段规定去重和排序；JSON 文件以一个 LF 结束；
- CSV 内嵌 JSON 使用同一 compact 规范，不追加 LF；
- run-specific 时间固定 UTC `YYYY-MM-DDTHH:MM:SSZ`，不写小数秒；
- 确定性 artifacts 不得包含生成时间、run-id 或绝对路径；`cleaning_run_id` 是冻结输入常量，可以
  出现在确定性文件中。

### 10.3 核心文件排序键

| 文件 | 固定行排序键 |
|---|---|
| `records_all.csv` | `source_dataset, source_record_id, record_key` |
| `compounds.csv` | `standardized_inchikey` |
| `compound_role_resolutions.csv` | `compound_id, dataset_role`，角色顺序 development→external |
| `conflict_reviews.csv` | `compound_id, dataset_role`，角色顺序 development→external |
| `compound_exclusions.csv` | `compound_id, dataset_role, exclusion_reason` |
| `record_exclusions.csv` | `source_dataset, source_record_id, exclusion_reason` |
| `duplicate_groups.csv` | `compound_id, dataset_role` |
| `structure_relation_edges.csv` | `comparison_scope, compound_id_a, dataset_role_a, compound_id_b, dataset_role_b, relation_type` |
| split CSV | `standardized_inchikey` |
| fold CSV | `standardized_inchikey` |
| `nearest_neighbors.csv` | `query_split, query_compound_id, nearest_split, nearest_compound_id` |
| 其他 pair 报告 | `compound_id_a, compound_id_b` 后接报告特有键 |

schema registry 声明的枚举 rank 优先于 Unicode 字典序：

```text
dataset_role: development < external
query_split: train < validation < external_test < external_tautomer_sensitivity
```

其他没有自定义 rank 的字符串才按 Unicode code point 排序。任何排序实现都必须显式使用 registry
rank，不能依赖 pandas categorical 的临时顺序或 locale。

所有其他 artifact 必须在 schema registry 中声明完整 schema 和排序键后才能生成；不存在“沿用当前
DataFrame 顺序”的输出。JSON object 的键顺序由 canonical JSON 规则确定。

## 11. 正式核心 artifacts

每个 audit/release 根下至少包含：

```text
modeling/records_all.csv
modeling/compounds.csv
modeling/compound_role_resolutions.csv
modeling/conflict_reviews.csv
modeling/compound_exclusions.csv
modeling/record_exclusions.csv
modeling/duplicate_groups.csv
modeling/structure_relation_edges.csv

splits/primary_reproduction/train.csv
splits/primary_reproduction/validation.csv
splits/primary_reproduction/train_tuning_cv_folds.csv
splits/full_development_stratified_cv_folds.csv
splits/full_development_scaffold_cv_folds.csv
splits/external_test.csv
splits/external_test_tautomer_clean_sensitivity.csv

reports/label_conflicts.csv
reports/cross_role_tautomer_overlaps.csv
reports/label_discordant_near_neighbors.csv
reports/nearest_neighbors.csv
reports/split_summary.csv
reports/source_label_crosstab.csv
reports/evidence_type_crosstab.csv
reports/source_label_association.csv
reports/descriptor_summary.csv
reports/descriptor_failures.csv
reports/scaffold_summary.csv
reports/similarity_summary.csv
reports/distribution_shift.csv
reports/leakage_audit.json
reports/resolution_summary.json
```

可以增加报告，但必须先进入 schema registry、manifest 和确定性文件集合，不能产生未登记结果。

## 12. 执行顺序与验收

执行顺序：

```text
测试
→ 首次 dry-run 和冲突计数裁决归档
→ 审查阈值裁决、重复、结构关系、泄漏、split 和分布报告
→ 审查重复、结构关系、泄漏、split 和分布报告
→ 批准最终 audit run-id
→ 正式运行到单一 release 根
→ 校验 pointer、manifest、逐文件哈希和行数
→ 独立审核
→ Git 提交
→ 标签 modeling-dataset-v1
```

验收条件：

- [ ] 每条来源记录具有稳定唯一 `record_key` 并可追溯；
- [ ] 每个有效标准键恰好一个 `compound_id`；
- [ ] 每个 compound-role 的标签、结构、泄漏状态独立且合法；
- [ ] 每个 exact duplicate group 有明确聚合结果；
- [ ] 每条 structure relation edge 的两端不同，标签不可比时显式记录；
- [ ] 全部确定性标签冲突均已按三步计数规则得到可追溯的排除或二分类结果；
- [ ] 阶段 1 的明确标签成员和标签保持不变；第 4 节第三步新增成员及标签在冲突裁决 artifact 中可追溯；
- [ ] 每个 eligible 主样本恰好属于一个主 split；
- [ ] development 与 primary external 无 exact/connectivity overlap；
- [ ] tautomer overlap 有报告和独立敏感性集；
- [ ] fixed validation 和 external 均未参与调参；
- [ ] 相同输入重跑的确定性 artifacts 哈希完全相同；
- [ ] audit、正式 release、pointer、manifest、日志和篡改拒绝链完整；
- [ ] 正式 release 通过独立审核并打 `modeling-dataset-v1` 标签。

## 13. 实现前约束

本策略再次审查通过后才实现 schema 和代码。首次实现不得直接生成正式 release，应依次完成：

1. schema registry、受控枚举和序列化器；
2. 三层数据模型、排除表和人工冲突模板；
3. input fingerprint、audit dry-run 和单 release 事务骨架；
4. duplicate groups、structure edges、泄漏和最近邻审计；
5. primary split、三套 CV 和 tautomer sensitivity split；
6. 描述统计、来源偏倚和分布漂移报告；
7. external 加载保护；
8. 确定性、非法状态、篡改、崩溃恢复、泄漏反例和端到端测试。

本策略通过前，不运行 dataset assembly dry-run，不创建 audit 或正式 release。
