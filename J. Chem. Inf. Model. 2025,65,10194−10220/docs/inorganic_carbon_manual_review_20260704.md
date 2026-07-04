# 疑似无机含碳结构人工审核清单

本清单来自审计批次 `20260704_100408_933902_UTC_07d4f39d`。原报告含 80 条来源记录，
按 `standard_inchikey` 合并后为 44 个唯一结构。

下表的“预审建议”用于保留决策前的审核记录。用户已完成最终决策：指定 6 个结构为
`exclude`，其余 38 个为 `include`，并已写入 `data/manual/inorganic_carbon_decisions.csv`。
本表中原有的空白“最终决策”列不再作为机器可读的决策源；以上 CSV 为唯一正式输入。
证据统计格式为 `P/N/U/X`，分别表示阳性、阴性、不确定和排除来源记录数。

### 用户指定的 6 个排除结构

1. `ATDGTVJJHBUTRL-UHFFFAOYSA-N` — Cyanogen bromide
2. `CRDYSYOERSZTHZ-UHFFFAOYSA-N` — Potassium selenocyanate
3. `JMANVNJQNLATNU-UHFFFAOYSA-N` — Cyanogen
4. `LSDPWZHWYPCBBB-UHFFFAOYSA-N` — Sodium methyl mercaptan
5. `QPJDMGCKMHUXFD-UHFFFAOYSA-N` — Chlorine cyanide
6. `YGYAWVDWMABLBF-UHFFFAOYSA-N` — Phosgene

## 审核表

| # | 预审建议 | Standard InChIKey | Parent SMILES | 来源 | 化学物名称 | 证据 P/N/U/X | 审核要点 | 最终决策 | 最终理由 | 审核人 |
|---:|---|---|---|---|---|---:|---|---|---|---|
| 1 | 建议排除 | `ATDGTVJJHBUTRL-UHFFFAOYSA-N` | `N#CBr` | IRIS | Cyanogen bromide | 0/0/1/0 | 氰的卤化物，无 C–H，通常视为拟卤素/无机边界化合物。 |  |  |  |
| 2 | 重点复核 | `BABMCXWQNSQAOC-UHFFFAOYSA-M` | `C[Hg]Cl` | CCRIS/CPDB | Methylmercury chloride | 8/32/13/0 | 有机汞化合物；结构明确但 Hg 可能超出常规有机 QSAR 适用域。 |  |  |  |
| 3 | 建议纳入 | `BAVYZALUXZFZLV-UHFFFAOYSA-N` | `CN` | CCRIS | Methylamine / methylamine hydrochloride | 0/0/0/2 | 去除带电对离子后为明确有机小分子甲胺。 |  |  |  |
| 4 | 建议纳入 | `BDAGIHXWWSANSR-UHFFFAOYSA-N` | `O=CO` | CCRIS/IRIS | Formic acid / sodium formate | 0/0/1/2 | 甲酸为明确有机羧酸；确认盐记录均已正确去对离子。 |  |  |  |
| 5 | 重点复核 | `CIJBKNZDKBKMFU-FIBGUPNXSA-N` | `[2H]C([2H])([2H])NN=O` | CCRIS | Potassium (Z)-ethanediazotate | 0/0/0/1 | 名称为钾盐，parent 为含氘同位素的有机片段；需核对原始结构与 E/Z 定义。 |  |  |  |
| 6 | 重点复核 | `CIJBKNZDKBKMFU-SUEIGJEOSA-N` | `C[15NH][15N]=O` | CCRIS | Potassium (E)-ethanediazotate | 0/0/0/1 | 名称为钾盐，parent 含 15N 同位素；需核对同位素和 E/Z 身份。 |  |  |  |
| 7 | 建议排除 | `CRDYSYOERSZTHZ-UHFFFAOYSA-N` | `N#C[SeH]` | CCRIS | Potassium selenocyanate | 0/0/0/1 | 无机盐/拟卤素边界；去钾后 parent 身份与原盐不完全等同。 |  |  |  |
| 8 | 重点复核 | `DBUXSCUEGJMZAE-UHFFFAOYSA-N` | `C[Hg+]` | CCRIS/IRIS | Methylmercury hydroxide / methylmercury | 0/0/1/1 | 有机汞阳离子，保留正电荷；需确认建模适用域和原物质身份。 |  |  |  |
| 9 | 建议纳入 | `DIKBFYAXUHHXCS-UHFFFAOYSA-N` | `BrC(Br)Br` | CCRIS/CPDB/IRIS | Bromoform / tribromomethane | 4/4/15/0 | 明确卤代有机物；标签证据存在冲突，结构决策与标签冲突处理分开。 |  |  |  |
| 10 | 重点复核 | `DKVNPHBNOWQYFE-UHFFFAOYSA-N` | `NC(=S)S` | CCRIS | Sodium diethyldithiocarbamate | 0/0/0/1 | 名称应含两个乙基，但 parent 为 `NC(=S)S`；名称与结构明显不符，建议回查或排除。 |  |  |  |
| 11 | 建议纳入 | `FJBFPHVGVWTDIP-UHFFFAOYSA-N` | `BrCBr` | CCRIS | Dibromomethane | 0/0/0/1 | 明确卤代甲烷。 |  |  |  |
| 12 | 建议纳入 | `FMWLUWPQPKEARP-UHFFFAOYSA-N` | `ClC(Cl)Br` | CCRIS/CPDB/IRIS | Bromodichloromethane | 25/8/20/0 | 明确卤代有机物；标签证据存在冲突。 |  |  |  |
| 13 | 建议纳入 | `GATVIKZLVQHOMN-UHFFFAOYSA-N` | `ClC(Br)Br` | CCRIS/CPDB/IRIS | Chlorodibromomethane | 1/4/14/0 | 明确卤代有机物；标签证据存在冲突。 |  |  |  |
| 14 | 建议纳入 | `GZUXJHMPEANEGY-UHFFFAOYSA-N` | `CBr` | CCRIS/CPDB/IRIS | Methyl bromide / bromomethane | 2/46/5/0 | 明确卤代有机物；证据以阴性为主但仍有冲突。 |  |  |  |
| 15 | 建议排除 | `HBMJWWWQQXIZIP-UHFFFAOYSA-N` | `[C-]#[SiH2+]` | CCRIS | Silicon carbide | 2/0/0/0 | 明确无机碳化物；当前 PubChem parent 表示也不适合常规有机 QSAR。 |  |  |  |
| 16 | 建议纳入 | `HDZGCSFEDULWCS-UHFFFAOYSA-N` | `CNN` | CCRIS/CPDB | Methylhydrazine / methylhydrazine sulfate | 17/6/15/0 | 明确有机肼；盐记录已去对离子，标签证据冲突。 |  |  |  |
| 17 | 建议纳入 | `HEDRZPFGACZZDS-UHFFFAOYSA-N` | `ClC(Cl)Cl` | CCRIS/CPDB/IRIS | Chloroform | 24/52/32/0 | 明确卤代有机物；标签证据冲突。 |  |  |  |
| 18 | 建议纳入 | `INQOMBQAUSQDDS-UHFFFAOYSA-N` | `CI` | CCRIS/IRIS | Methyl iodide | 4/0/1/0 | 明确卤代有机物。 |  |  |  |
| 19 | 重点复核 | `IYKVLICPFCEZOF-UHFFFAOYSA-N` | `NC(N)=[Se]` | IRIS | Selenourea | 0/0/1/0 | 有机硒化合物；结构明确，但 Se 的特征支持和适用域需确认。 |  |  |  |
| 20 | 建议排除 | `JMANVNJQNLATNU-UHFFFAOYSA-N` | `N#CC#N` | IRIS | Cyanogen | 0/0/1/0 | 无氢拟卤素小分子，建议按无机边界物排除。 |  |  |  |
| 21 | 建议纳入 | `JPOXNPPZZKNXOV-UHFFFAOYSA-N` | `ClCBr` | CCRIS/IRIS | Bromochloromethane | 0/0/1/1 | 明确卤代有机物。 |  |  |  |
| 22 | 重点复核 | `KTQYJQFGNYHXMB-UHFFFAOYSA-N` | `C[Si](Cl)Cl` | CCRIS | Methyldichlorosilane | 0/0/0/1 | 有机硅化合物；结构明确，但 Si 特征和适用域需确认。 |  |  |  |
| 23 | 重点复核 | `LSDPWZHWYPCBBB-UHFFFAOYSA-N` | `CS` | CCRIS | Sodium methyl mercaptan | 0/0/0/1 | 名称为钠盐，parent 已变为甲硫醇；需确认去盐后身份是否可接受。 |  |  |  |
| 24 | 建议纳入 | `LYGJENNIWJXYER-UHFFFAOYSA-N` | `C[N+](=O)[O-]` | CCRIS/CPDB | Nitromethane | 13/9/21/0 | 明确有机硝基化合物；标签证据冲突。 |  |  |  |
| 25 | 建议纳入 | `MEUKEBNAABNAEX-UHFFFAOYSA-N` | `COO` | CCRIS | Methyl hydroperoxide | 0/0/0/1 | 明确有机过氧化物。 |  |  |  |
| 26 | 建议纳入 | `NEHMKBQYUWJMIP-UHFFFAOYSA-N` | `CCl` | CCRIS/IRIS | Methyl chloride / chloromethane | 0/0/2/1 | 明确卤代有机物。 |  |  |  |
| 27 | 建议纳入 | `NZZFYRREKKOMAT-UHFFFAOYSA-N` | `ICI` | CCRIS | Diiodomethane | 0/0/0/1 | 明确卤代有机物。 |  |  |  |
| 28 | 建议纳入 | `OKJPEAGHQZHRQV-UHFFFAOYSA-N` | `IC(I)I` | CCRIS/CPDB | Iodoform | 0/9/7/0 | 明确卤代有机物。 |  |  |  |
| 29 | 建议纳入 | `OKKJLVBELUTLKV-UHFFFAOYSA-N` | `CO` | CCRIS/IRIS | Methanol | 0/0/1/1 | 明确有机醇。 |  |  |  |
| 30 | 重点复核 | `OXBIRPQQKCQWGV-UHFFFAOYSA-N` | `C[As](O)O` | CCRIS | Methylarsonous acid | 0/0/0/1 | 有机砷化合物；需确认 As 特征、价态和模型适用域。 |  |  |  |
| 31 | 建议排除 | `QPJDMGCKMHUXFD-UHFFFAOYSA-N` | `N#CCl` | IRIS | Chlorine cyanide | 0/0/1/0 | 氰的卤化物，无 C–H，通常视为拟卤素/无机边界化合物。 |  |  |  |
| 32 | 建议纳入 | `SQDFHQJTAWCFIB-UHFFFAOYSA-N` | `C=NO` | CCRIS | Formaldoxime | 0/0/0/1 | 明确有机肟。 |  |  |  |
| 33 | 建议纳入 | `UMGDCJDMYOKAJW-UHFFFAOYSA-N` | `NC(N)=S` | CCRIS/CPDB | Thiourea | 5/10/3/0 | 明确有机含硫化合物；标签证据冲突。 |  |  |  |
| 34 | 建议纳入 | `VOPWNXZWBYDODV-UHFFFAOYSA-N` | `FC(F)Cl` | CCRIS/CPDB/IRIS | Chlorodifluoromethane | 0/18/1/0 | 明确卤代有机物。 |  |  |  |
| 35 | 建议纳入 | `WSFSSNUMVMOOMR-UHFFFAOYSA-N` | `C=O` | CCRIS/CPDB/IRIS | Formaldehyde | 25/21/37/0 | 明确有机醛；标签证据冲突。 |  |  |  |
| 36 | 建议纳入 | `XSQUKJJJFZCRTK-UHFFFAOYSA-N` | `NC(N)=O` | CCRIS/CPDB/IRIS | Urea | 0/6/5/1 | 明确有机酰胺类化合物。 |  |  |  |
| 37 | 建议纳入 | `XWCDCDSDNJVCLO-UHFFFAOYSA-N` | `FCCl` | CCRIS/CPDB | Chlorofluoromethane | 9/0/0/0 | 明确卤代有机物。 |  |  |  |
| 38 | 建议纳入 | `XZBIXDPGRMLSTC-UHFFFAOYSA-N` | `NNC=O` | CPDB | Formylhydrazine | 2/0/2/0 | 明确有机肼/酰胺类化合物。 |  |  |  |
| 39 | 重点复核 | `YAHQGPVDZBJVST-NSCUHMNNSA-N` | `[H]/N=N/CO` | CCRIS | Potassium (E/Z)-methanediazotate | 0/0/0/2 | 两个 E/Z 名称聚合到同一结构；需核对原始立体和去钾后身份。 |  |  |  |
| 40 | 重点复核 | `YGYAWVDWMABLBF-UHFFFAOYSA-N` | `O=C(Cl)Cl` | IRIS | Phosgene | 0/0/1/0 | 无 C–H 的羰基卤化物；常可作有机试剂，但是否纳入本项目有机 QSAR 需明确政策。 |  |  |  |
| 41 | 建议纳入 | `YMWUJEATGCHHMB-UHFFFAOYSA-N` | `ClCCl` | CCRIS/CPDB/IRIS | Dichloromethane / methylene chloride | 32/36/70/0 | 明确卤代有机物；标签证据冲突。 |  |  |  |
| 42 | 建议纳入 | `YXHKONLOYHBTNS-UHFFFAOYSA-N` | `C=[N+]=[N-]` | CCRIS/IRIS | Diazomethane | 2/0/1/0 | 明确有机重氮化合物。 |  |  |  |
| 43 | 建议纳入 | `ZHNUHDYFZUAESO-UHFFFAOYSA-N` | `NC=O` | CCRIS | Formamide | 0/2/2/0 | 明确有机酰胺。 |  |  |  |
| 44 | 重点复核 | `ZKGSUVMABCXPKK-UHFFFAOYSA-N` | `C[As](I)I` | CCRIS | Diiodomethylarsine | 0/0/0/1 | 有机砷化合物；需确认 As 特征、原始结构和模型适用域。 |  |  |  |

## 数量汇总

- 建议纳入：27 个。
- 建议排除：5 个。
- 重点复核：12 个。
- 用户最终决策：`include` 38 个，`exclude` 6 个，共 44 个。

## 建议的审核顺序

1. 先确认 5 个“建议排除”的无机/拟卤素边界结构。
2. 回查 `SODIUM DIETHYLDITHIOCARBAMATE` 的名称–结构不一致。
3. 确定 Hg、As、Si、Se 化合物是否在模型适用域内。
4. 核对钾重氮酸盐的去盐、同位素和 E/Z 立体表示。
5. 对其余明确有机小分子逐项确认纳入，并填写审核人和理由。

## 决策回填

审核完成后，将每个 InChIKey 的最终结果填入
`data/manual/inorganic_carbon_decisions.csv`：

```text
standard_inchikey,decision,review_reason,reviewer
<InChIKey>,include|exclude,<审核理由>,<审核人>
```

决策文件变更后必须重新执行 `--dry-run`，并审核新批次；当前批次不得直接用于正式提交。
