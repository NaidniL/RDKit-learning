# 模型批次 1：训练与 external 隔离策略

训练唯一入口是 `releases/dataset_assembly/current_release.json`。程序先验证 pointer schema、
manifest SHA-256、formal manifest schema、release ID、路径安全、全部 artifact 的 SHA-256/字节数/
逻辑行数/schema/列顺序，以及无额外或缺失文件和无 symlink。训练代码不得读取 `data/splits/v1/`、
审计目录或手写 CSV 路径。

默认开发数据仅为 `primary_reproduction/train.csv`、`validation.csv` 和
`train_tuning_cv_folds.csv`。超参仅允许由 train 内固定 folds 选择；validation 仅用于固定模型候选的
开发期选择。full-development stratified/scaffold CV 仅可作为论文复现或稳健性报告，不能回流为调参依据。

特征只能从 `canonical_smiles` 或 `parent_smiles` 构造。批准的第一批为 ECFP4 (radius=2, 2048 bits)、
MACCS、RDKit descriptors 和 physicochemical descriptors。`source_dataset`、`dataset_role`、
`evidence_type`、`source_record_id`、`label_resolution_sources_json`、`review_status`、
`leakage_status` 以及标签、ID、fold 字段均为禁止特征。

模型批次 1 可输出 train 内 CV 指标、validation 指标、train 内 CV 选出的参数、模型、feature manifest 与
experiment manifest。不得输出任何 external 指标、external 混淆矩阵或 external 预测 CSV。阈值、特征选择、early stopping、
校准和模型选择均不得读取 external。只有独立审核并冻结最终实验 manifest 后，才可由后续流程解锁
`external_final`。

## LogisticRegression baseline

LogisticRegression 固定使用 `penalty=l2`、`solver=liblinear`、`max_iter=5000` 和固定 random seed。
指纹列保持原值（ECFP4 radius=2, 2048 bits；MACCS 167 bits）；连续 descriptor 列在每个训练折内依次
执行 median imputation、常数列移除与 `StandardScaler`。validation 永不参与任一预处理器的 `fit`。

第一轮允许的特征组合为 `ecfp4`、`maccs`、`rdkit_descriptors` 与四者组合。C 的最小搜索网格为
`[0.01, 0.03, 0.1, 0.3, 1, 3, 10]`，只以 train 内固定 folds 的 AUROC 选择，随后以完整 train 重训；
validation 只评估一次，threshold 固定为 0.5。`class_weight=balanced` 仅能作为显式记录的独立实验变量。

开发期报告 AUROC、AUPRC、log loss、Brier、accuracy、balanced accuracy、MCC、sensitivity、specificity、
F1 及聚合 validation confusion counts；不写 prediction 文件，仅把带 compound ID 和标签的 validation 预测
序列以 canonical digest 记录在 manifest。任何 `ConvergenceWarning` 均直接失败，不允许静默忽略。

## Dummy 训练链路体检

在任何学习型 baseline 之前，必须分别运行 `DummyClassifier(strategy="most_frequent")` 和
`DummyClassifier(strategy="stratified", random_state=42)`。前者强制断言 validation 预测恒为 train
多数类、accuracy 等于 validation 中该类的占比、常数概率的 AUROC 为 0.5（两类均存在时）且 MCC 为
0；后者强制断言相同 seed 的预测与概率完全一致。

体检在特征化后断言 train/validation 的 `compound_id` 唯一、彼此不相交、标签仅为 0/1，且 X、y 和
split 行顺序一致。Dummy 体检只读取 train/validation，experiment manifest 只记录实际读取的获准 split
artifact hashes、样本数与类别计数、dummy 策略与 seed、训练/validation 指标、feature/model hashes、
runtime signature 与 code revision。没有
正例（负例）时 sensitivity（specificity）记录为 `null`；单类标签时 AUROC 为 `null`；MCC 分母退化时
固定记录为 `0.0`。

## 模型批次 2：树模型与预注册选择规则

候选模型族固定为 LogisticRegression、RandomForestClassifier 和 LightGBM；特征候选固定为 ECFP4、
MACCS、RDKit+physicochemical descriptors 与四者混合。每个模型族与特征候选只允许一轮预设
train-tuning CV 网格搜索；每个候选在 fixed validation 上只评估一次。不得根据 validation 结果扩展网格、
筛选特征或调整阈值。

最终选择规则预注册为：主指标 validation AUROC；次级指标依次为 AUPRC、MCC、sensitivity、specificity；
AUROC 并列时，选择更简单的 feature set、较少预处理步骤、随后选择 train-tuning CV fold 间方差更低的
候选。模型与阈值冻结、独立审核完成前，external 始终锁定。

RandomForest 不缩放指纹或 descriptor；descriptor 缺失值只由训练折拟合的 median imputer 处理。RF 网格
固定为 `n_estimators=[300,500]`、`max_features=[sqrt,log2]`、`min_samples_leaf=[1,2,5]`、
`class_weight=[None,balanced]`。LightGBM 固定 `random_state=42`、`n_jobs=1`、`deterministic=true`，
网格为 `num_leaves=[15,31,63]`、`learning_rate=[0.03,0.1]`、`n_estimators=[100,300]`、
`min_child_samples=[10,20,50]`、`reg_lambda=[0,1,10]`。
