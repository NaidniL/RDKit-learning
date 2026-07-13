# 模型批次 2：预注册候选排序报告

状态：`CANDIDATE RANKING COMPLETE — NOT FROZEN`。

本报告只汇总 development 数据。所有候选使用同一正式 dataset release、固定
`train_tuning_cv` 调参协议和一次 fixed validation 评估；全部 experiment manifest 的
`external_access` 均为 `denied`。未读取、计算或输出任何 external 指标、预测或 digest。

策略文件 SHA-256：`e56583f94f71326fce2d59f63c4027b18445403b27c18eddfc141881cd5cdc10`。

## 机械排序规则

1. validation AUROC 降序；
2. 仅在 AUROC 完全相同时，比较 feature set 简单度；
3. 再比较预处理步骤数量；
4. 再比较 train-tuning CV fold 间 AUROC 方差。

本批次 manifest v1 记录的是 train-tuning CV 的 pooled OOF AUROC，未记录每折 AUROC，因此第 4 条
尚未被调用；前两名 AUROC 不相同，排序无需 tie-breaker。

## 排序表

| Rank | Model family | Feature set | Selected train-CV params | Train CV OOF AUROC | Validation AUROC | AUPRC | MCC | Sensitivity | Specificity | Confusion (TN/FP/FN/TP) | Feature shape / preprocessing | Manifest SHA-256 | Validation prediction digest | External |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| 1 | LightGBM | descriptors | leaves=31, lr=0.03, estimators=300, min_child=10, lambda=0 | 0.8017 | **0.7659** | 0.7896 | 0.3806 | 0.6786 | 0.7030 | 71/30/27/57 | 736×220 dense; 12 imputed, 11 constants removed, 209 final | `66d04fe…ef116` | `f8c9c201…16e9` | denied |
| 2 | LightGBM | mixed | leaves=31, lr=0.1, estimators=300, min_child=20, lambda=1 | 0.8018 | 0.7653 | 0.7896 | 0.3588 | 0.6667 | 0.6931 | 70/31/28/56 | 736×2435 dense; 12 imputed, 11 constants removed, 2424 final | `11f25090…0517d` | `b021bb51…e9dd8` | denied |
| 3 | RandomForest | MACCS | trees=500, sqrt, leaf=1, class_weight=None | 0.8057 | 0.7515 | 0.7636 | 0.3883 | 0.6548 | 0.7327 | 74/27/29/55 | 736×167 sparse CSR; no descriptor preprocessing | `b0b409bd…82fdd` | `676db888…b5fa1` | denied |
| 4 | RandomForest | descriptors | trees=300, log2, leaf=1, class_weight=balanced | 0.8136 | 0.7514 | 0.7741 | **0.3968** | 0.6190 | 0.7723 | 78/23/32/52 | 736×220 dense; 12 imputed, 11 constants removed, 209 final | `fe05dc6e…0cab9` | `c5059198…e6450` | denied |
| 5 | RandomForest | mixed | trees=500, log2, leaf=1, class_weight=balanced | **0.8207** | 0.7512 | 0.7736 | 0.3856 | 0.6071 | 0.7723 | 78/23/33/51 | 736×2435 dense; 12 imputed, 11 constants removed, 2424 final | `018f35b6…9ddb` | `60d94ef5…5364` | denied |
| 6 | LightGBM | MACCS | leaves=15, lr=0.03, estimators=300, min_child=10, lambda=0 | 0.8015 | 0.7228 | 0.7439 | 0.3769 | 0.6429 | 0.7327 | 74/27/30/54 | 736×167 sparse CSR; no descriptor preprocessing | `361999e4…75102` | `6de8fda9…572d3` | denied |
| 7 | RandomForest | ECFP4 | trees=300, log2, leaf=1, class_weight=None | 0.8012 | 0.7210 | 0.7341 | 0.3744 | 0.5952 | 0.7723 | 78/23/34/50 | 736×2048 sparse CSR | `ede50be4…b3fe5` | `1070f02e…3673c` | denied |
| 8 | LightGBM | ECFP4 | leaves=31, lr=0.03, estimators=300, min_child=10, lambda=0 | 0.7844 | 0.6973 | 0.7014 | 0.2853 | 0.6429 | 0.6436 | 65/36/30/54 | 736×2048 sparse CSR | `2ef8096e…b3375` | `d0806995…4dfa1` | denied |

完整 SHA-256 和 digest 位于各自 experiment manifest；为便于表格阅读，此处只显示前后片段。

## 结果与下一步

按已登记的主选择指标，当前 `proposed final config` 是 **LightGBM + descriptors**，因为其 validation
AUROC 为 0.7659123055，是完整树模型候选集中唯一最高值。该结论不等同于模型冻结：尚未执行模型冻结前
审核、独立审核、最终 artifact 冻结或 external evaluation。

在下一步审核前不得训练 final、不得解锁 `external_final`，也不得修改候选网格、阈值或选择规则。
