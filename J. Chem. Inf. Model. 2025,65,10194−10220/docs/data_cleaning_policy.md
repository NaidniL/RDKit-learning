# 数据清洗策略 - 待审查稿

本文档说明 `scripts/clean_datasets.py` 的处理规则。清洗程序尚未运行，请在生成
processed 数据前审查以下规则。

## 与原论文方法的关系

原论文明确报告了以下数据准备步骤：

1. 检查 canonical SMILES 和毒性终点的缺失情况；
2. 使用 RDKit 检查 canonical SMILES；
3. 筛查重复记录；
4. 从训练数据中移除与外部测试集重叠的分子；
5. 从相应测试集或挑战集中排除无机物、混合物、结构定义不明确和结构缺失的记录；
6. 仅使用 IRIS A 类和 E 类作为明确的人类致癌与非致癌标签。

原论文以此前已经整理好的合并数据集为起点，没有公开完整的来源级标签映射和冲突
处理规则。因此，下面的详细映射属于本项目规则，不应视为对论文未公开步骤的复述。

## 输出层级

### 严格的模型就绪数据集

- `development_pool.csv`：具有明确 CPDB/IRIS 二分类标签且结构可建模的数据。
- `train.csv`、`validation.csv`：默认按标签分层随机划分为 80:20，随机种子为 42。
- `external_ccris_test.csv`：具有明确 CCRIS 致癌性标签，且不与任何有效
  CPDB/IRIS 结构重叠的数据。

### 保留用于审查的数据集

- `development_review_candidates.csv`：CPDB/IRIS 中方向一致但证据较弱的候选，
  可在独立人工核查后用于敏感性分析。
- `external_review_candidates.csv`：CCRIS 中证据较弱的外部集候选，仅供外部评估
  研究，不得加入训练集。
- `uncertain_set.csv`：结构有效，但没有明确二分类标签的数据。
- `conflict_set.csv`：同一 standard InChIKey 同时存在明确阳性和明确阴性记录的数据。
- `discordant_evidence_set.csv`：明确标签与相反方向弱证据并存的数据。这些记录可保留在
  主训练集，但必须进行人工核查和敏感性分析。
- `structure_representation_conflict.csv`：互变异构体规范化后，同一 standard InChIKey
  仍对应多个 parent SMILES 的异常记录。
- `inorganic_carbon_review.csv`：未列入明确无机规则的单碳小分子，以及小型无氢
  多碳边界结构。报告保留待审核和已审核记录及其决策、理由和审核人。
- `excluded_set.csv`：结构无效或缺失，以及只有非致癌性终点的 CCRIS 记录。
- `source_records_audit.csv`：所有标准化后的来源证据记录，包括原始标签、来源结构
  标识和 JSON 证据。

## 来源标签规则

### CPDB

| 来源代码 | 严格类别 | 候选方向 | 理由 |
|---|---|---|---|
| `+`、`c` | positive | positive | 作者判断为诱发肿瘤或 NCI/NTP 明确证据 |
| `-` | negative | negative | 作者或 NCI/NTP 判断为阴性 |
| `p`、`a` | uncertain | positive | 部分证据、相关证据或提示性证据 |
| `e` | uncertain | none | 证据不明确 |
| `0`、空值 | uncertain | none | 没有明确判断 |
| `inad=i` | uncertain | none | 实验被判定为不足 |

严格策略不会把 `p` 或 `a` 直接提升为阳性标签。这些记录仍保留在
`development_review_candidates.csv` 中。

### IRIS

严格阳性标签：

- `A (Human carcinogen)`
- `Carcinogenic to humans`

严格阴性标签：

- `E (Evidence of non-carcinogenicity for humans)`

probable、possible、likely 和 suggestive 等描述保留为阳性候选，但不进入严格训练集。
`Not likely to be carcinogenic to humans` 可能仅适用于特定暴露途径或剂量条件，
因此降级为阴性候选，不作为全局严格阴性。D 类、证据不足和无法判定等描述保留为
uncertain。

### CCRIS

只有 `carcinogenicity_studies_json` 中的记录有资格用于致癌性标签。致突变性、促肿瘤
和肿瘤抑制记录绝不转换为致癌性阴性标签。

- 只有规范化后完全等于 `POSITIVE` 或 `NEGATIVE` 的结果才进入严格白名单；
- 任何带限定语的结果，即使以 `POSITIVE` 或 `NEGATIVE` 开头，也不直接作为高置信标签；
- 如果仍能判断证据方向，将方向保留为中置信候选，其余记录保留为 uncertain；
- `raw_label_mapping_report.csv` 会列出所有唯一 `rsltc` 文本及频数，供正式运行前人工审查。

## 结构处理规则

1. 使用 RDKit 解析来源 SMILES。
2. 应用 RDKit cleanup，并对来源结构生成 canonical SMILES。
3. 先识别明确无机含碳图结构，包括元素碳、氰根、一氧化碳、二氧化碳、碳酸根/碳酸氢根、
   氰酸根、硫氰酸根、羰基硫和二硫化碳。纯碳阴离子自动规则仅覆盖无氢单碳阴离子，
   以及最多两个碳、只含一个三键的明确乙炔化物图结构。环戊二烯基等有机碳负离子
   不得自动归类为碳化物；其他纯碳阴离子先进入人工审核。
4. 明确无机含碳片段单独出现时作为无机物排除；只有形式电荷非零的额外片段
   才可作为对离子自动移除。
5. 移除明确无机含碳片段后，要求恰好存在一个候选含碳 parent。
6. 其余不含 C-C 键、重原子数不超过 4 的单碳小分子，以及重原子数不超过 5、
   不含碳连氢且仅含 C/N/O/S 的多碳边界结构，进入人工审核集。它们不在未审核
   状态下进入严格模型集，以保留甲醛、甲酸等可能的有机物供人工决策。
7. 人工决策通过 `data/manual/inorganic_carbon_decisions.csv` 重新输入流程。`include`
   表示允许该结构参与后续建模资格判定，`exclude` 表示人工排除；两者都必须填写理由
   和审核人。未决策结构继续留在审核集中。
8. 对只有一个有机 parent 的盐，仅在 parent 与所有额外片段异号、额外片段总电荷
   非零且整体电荷完全配平时，才允许移除对离子。中性 parent 加离子、同号离子或计量
   不配平结构均作为无法确认的多片段离子结构排除。无额外片段的单片段永久离子仍可保留。
9. 多个有机片段，或有机 parent 与任何中性额外片段共存时，按混合物、溶剂化物或
   加合物排除。中性 CO₂、CO、COS、CS₂、水和氨均不得当作对离子静默移除。
10. 排除含通配符或查询原子的结构、无碳结构、少于两个重原子的结构、标准化失败的
   结构，以及无法生成 standard InChIKey 的结构。
11. 尝试使用 RDKit `Uncharger` 规范化可中和电荷；允许永久离子保留形式电荷。
12. 记录 `formal_charge_before`、`formal_charge_after`、`uncharging_applied` 和
   `residual_charge`。
13. 使用 RDKit `TautomerEnumerator().Canonicalize()` 对 parent 进行 canonical tautomer
   规范化，消除同一 standard InChIKey 因输入顺序选中不同 parent SMILES 的风险。
   显式设置 `SetRemoveSp3Stereo(False)` 以保留四面体手性中心，并使用
   `SetReassignStereo(True)` 重新分配规范化后仍然有效的立体信息。参与互变异构的双键立体信息
   继续采用 RDKit 默认处理。
14. canonical SMILES 和 parent SMILES 均保留可用的立体化学信息。parent 先写为
    canonical isomeric SMILES，并用锁定 RDKit 立即回读；只有默认表示无法回读或
    回读后完整 InChIKey 改变时，才惰性尝试 canonical Kekulé SMILES。
15. 从规范化后的 parent 生成 standard InChIKey、前 14 位 `connectivity_key` 和
    Bemis-Murcko scaffold；scaffold 必须从已安全回读的 parent 分子生成，不得从
    不可序列化复现的中间内存状态生成。最终 parent SMILES 必须可回读且回读后完整 InChIKey
    与内存 parent 完全一致；默认与 Kekulé 表示均不满足时标准化失败。
16. 分别记录 `rdkit_parse_ok`、`model_structure_ok` 和
    `leakage_connectivity_keys_json`：原始结构能解析不等于可建模，被排除的多片段结构仍保留
    其所有潜在有机组分的连接层键。
17. 结构表的 `source`、`source_record_id`、`structure_status` 和 IRIS DTXSID
    必须通过一致性校验。只接受 `ok`、`resolved` 和 `matched` 状态；其他状态不会进入
    RDKit 标准化。
18. IRIS 关联键优先使用 DTXSID，其次使用有效 CASRN。当 DTXSID 缺失且 CASRN 为
    `Various`、`N/A` 等占位值时，标签表与结构表共同使用规范化化学名称的 SHA-256
    前 16 位生成 `IRIS-NAME:<digest>`，防止多个占位 CASRN 形成重复关联键。DTXSID 必须匹配
    `DTXSID<数字>`，CASRN 必须同时通过格式和校验位检查；非占位但非法的标识符直接报错，
    不回退到名称哈希。DTXSID 在标签、结构关联和审计字段中统一规范为大写；当名称本身也是
    `N/A`、`Unknown`、`Various` 等占位值时，禁止生成名称哈希键。

## 去重与数据泄漏控制

- 按完整 standard InChIKey 聚合证据。
- 同时存在明确阳性与明确阴性证据时，标签设为 `conflict`。
- 外部 CCRIS 与 CPDB/IRIS 的泄漏检查使用 `connectivity_key`，因此立体异构体、同位素差异或
  部分质子化状态差异不会在二维特征模型中逃逸重叠检查。
- 外部泄漏键使用所有 `rdkit_parse_ok` 的 CPDB/IRIS 来源结构生成。对于中性溶剂化物、
  加合物或多有机片段混合物，即使整体不可建模，`leakage_connectivity_keys_json` 中的每个
  潜在有机组分仍参与外部重叠拦截。
- 默认划分复刻论文的标签分层随机 80:20 方案。
- `--split-method scaffold` 作为扩展方案。Murcko scaffold 生成时不保留立体标记，并按
  “共享 scaffold 或共享 `connectivity_key`”的连通分量生成最终 group，因此有环和无环的同连接
  结构都不会被拆分。
- 骨架划分要求训练集和验证集都包含两个类别，并同时优化样本量与两个子集的阳性率偏差。
- scaffold 候选搜索在评分前即排除任何 `connectivity_key` 重叠方案，输出后再次断言互斥。
- 随机划分会额外生成 `connectivity_overlap_report.csv`，报告训练集/验证集之间的连接层重叠。
- `uncertain_set.csv` 和 `conflict_set.csv` 保留全部 external 化合物，并通过
  `external_overlap` 标记其是否与 development 重叠。

## 工程保护与审计运行

- JSON 试验字段必须是 `list[dict]`，解析错误会报告数据源、记录 ID 和字段。
- 合并三个标签来源后，强制校验 `source_record_id` 非空且在各数据源内唯一；重复时直接报错，
  不静默去重。
- 化合物聚合结果使用固定列模式，即使结果为空也会生成带表头的空 CSV。
- 三个结构表全空时仍保留固定结构列模式；全部来源数据都为空时，在合并后立即报出
  “所有来源数据均为空，无法构建开发集”，不进入人工决策或划分流程。
- 如果严格开发集为空或未同时包含阳性和阴性类别，数据划分前会给出明确错误。
- 输出前检查 InChIKey 唯一性、二分类标签、划分完整性以及开发集/外部集的连接层互斥性。
- 每次 `--dry-run` 会生成唯一的 `run-id`，并将审计报告永久保存到
  `reports/cleaning/audits/<run-id>/`，不覆盖旧批次，也不写入 `data/processed/`。
- dry-run 会同时将所有拟发布 CSV 保存到 `reports/cleaning/audits/<run-id>/datasets/`，
  因此人工审核的是实际拟发布数据，不仅是统计报告。
- 审计批次中的 `cleaning_manifest.json` 记录原始文件、人工决策、全部项目清洗模块、
  入口脚本、可用的依赖锁定文件、划分参数和运行环境共同生成的输入指纹。
- 运行环境签名包含 Python、操作系统平台、机器架构、RDKit、NumPy、pandas、scikit-learn
  和 InChI 实现签名。新版 RDKit 优先使用 `Chem.GetInchiVersion()`；当前固定的 RDKit 2023.09.6
  无该 API，因此从 `rdinchi` 帮助日志解析 InChI Software 版本，并同时记录 InChI 扩展与
  链接库的二进制 SHA-256。动态库发现同时覆盖 `rdkit/.dylibs`、`rdkit/.libs` 和 Linux wheel
  常用的同级 `rdkit.libs`。版本解析失败时直接报错。
- 清单对每个拟发布 CSV、每个审核报告 CSV 记录 SHA-256 和数据行数，并记录
  `cleaning_log.md` 的 SHA-256。
- 正式运行必须使用 `--approved-audit-run <run-id>` 引用已审核批次；当前指纹与该批次
  不一致时直接拒绝生成正式数据。
- 正式运行重新生成全部 staged CSV，逐文件比较哈希和行数；文件集合、字节内容或行数
  有任何差异时，在目录事务提交前拒绝运行。
- 正式运行在重新计算之前，先重新校验审计目录中的数据文件集、报告文件集、逐文件哈希、
  行数和日志哈希；人工审核后的编辑、截断、替换或文件增删都会阻止正式运行。
- 正式清洗报告保存在 `reports/cleaning/current/`。`data/processed/` 和
  `reports/cleaning/current/` 先完整写入临时目录，再在同一事务中替换；审计历史不参与替换。
- 日志记录 Python、RDKit、pandas、scikit-learn、实际 InChI 库版本、原始文件校验和排除原因。
- 化合物级的标准化备注会合并所有来源记录；布尔处理标志使用 `any()` 聚合，
  `formal_charge_before` 保留唯一值 JSON 列表，`formal_charge_after` 必须在组内一致。
- `tests/test_cleaning.py` 包含手性保留、空聚合列模式、碳化物反例、离子配平、中性共组分、
  被排除组分的泄漏拦截、人工决策、开发集/外部集候选隔离、代码与环境指纹、InChI 旧版回退、
  `rdkit.libs` 动态库发现、全空输入、审计数据/报告/日志篡改、拟输出哈希、重复来源 ID 和
  scaffold 连通分量隔离的回归测试。

## 审查通过后拟执行的命令

```bash
source .venv/bin/activate
python scripts/clean_datasets.py --split-method random --dry-run
```

首次执行必须使用 `--dry-run`，审查 `raw_label_mapping_report.csv`、排除原因、重叠报告和样本量后，
使用该目录名中的 `run-id` 生成正式 processed 数据：

```bash
python scripts/clean_datasets.py --split-method random --approved-audit-run <run-id>
```

本次修改不运行上述任何清洗命令。
