# v1 descriptor SHAP diagnostic

状态：`POST HOC, MODEL FROZEN`。

本报告只读取冻结 v1 model、preprocessing artifact 与 formal release 的 train/validation CSV。它不读取 external split，也不会改变模型、特征、预处理或 threshold。SHAP 归因描述该模型在 refit 数据上的关联，不构成因果或机制结论。

## Locked inputs

- final training manifest SHA-256: `8bd0f85e8f5a8309f534beb2247f4513fb656dfd374fdbcb50b164aabaaa3f5b`
- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- samples: `921` (train+validation)
- retained descriptors: `209`
- SHAP package: `0.46.0`
- global attribution figure: `reports/figures/v1_descriptor_shap_global.png`

## Top global descriptor attributions

| Rank | Descriptor | Mean \|SHAP\| | Mean SHAP | LightGBM split importance |
|---:|---|---:|---:|---:|
| 1 | rdkit_fr_nitroso | 0.588751 | 0.041102 | 97 |
| 2 | rdkit_PEOE_VSA5 | 0.281204 | 0.018653 | 78 |
| 3 | rdkit_BertzCT | 0.275142 | 0.028131 | 188 |
| 4 | rdkit_VSA_EState8 | 0.226785 | -0.016030 | 193 |
| 5 | rdkit_qed | 0.202302 | 0.000733 | 193 |
| 6 | rdkit_SlogP_VSA8 | 0.171665 | 0.014931 | 87 |
| 7 | rdkit_MinAbsEStateIndex | 0.161396 | -0.008934 | 246 |
| 8 | rdkit_VSA_EState5 | 0.156612 | -0.012498 | 156 |
| 9 | rdkit_Kappa3 | 0.154132 | -0.005799 | 174 |
| 10 | rdkit_BCUT2D_MWLOW | 0.149129 | -0.010392 | 143 |
| 11 | rdkit_BCUT2D_MRLOW | 0.139095 | -0.018670 | 220 |
| 12 | rdkit_HallKierAlpha | 0.137042 | 0.007241 | 133 |
| 13 | rdkit_BCUT2D_MRHI | 0.134388 | -0.007787 | 226 |
| 14 | rdkit_BalabanJ | 0.129580 | 0.012830 | 167 |
| 15 | rdkit_MaxAbsPartialCharge | 0.128926 | 0.001089 | 86 |
| 16 | rdkit_SlogP_VSA6 | 0.126224 | -0.005581 | 118 |
| 17 | rdkit_FpDensityMorgan2 | 0.126099 | 0.001956 | 122 |
| 18 | rdkit_SlogP_VSA3 | 0.122242 | -0.000428 | 66 |
| 19 | rdkit_SMR_VSA4 | 0.109175 | 0.003647 | 56 |
| 20 | rdkit_AvgIpc | 0.108275 | 0.008104 | 170 |

## Interpretation boundary

- Feature rankings are global attributions for the frozen train+validation refit data, not an external performance analysis.
- Mean signed SHAP values aggregate directions across the refit data; feature-level dependence and individual-compound explanations require separate descriptive reports.
- Any future uncertainty, applicability-domain, or consensus policy must be designed and evaluated on development data without using the locked v1 external result as feedback.
