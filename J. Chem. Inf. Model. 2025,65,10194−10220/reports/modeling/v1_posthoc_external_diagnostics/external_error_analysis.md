# v1 post-hoc primary external error analysis

状态：`COMPLETE — DESCRIPTIVE ONLY`。

本报告在显式 post-hoc 授权下复现冻结 v1 的 primary external predictions。它没有改变模型、特征、预处理、阈值或选择规则，也没有写出样本级 prediction 文件。

## Reproduced aggregate errors

- TN / FP / FN / TP: `130 / 69 / 93 / 163`
- prediction digest reproduced: `8b82d1dd93f9da4dd2c9ec55b19f0b7b47d3522dfc814b2f2915e8ceda4b3f5e`

## false positive vs true negative descriptor profile

| Descriptor | Left mean | Right mean | SMD |
|---|---:|---:|---:|
| rdkit_SlogP_VSA8 | 19.110922 | 4.019348 | 1.264354 |
| rdkit_NumAromaticRings | 2.666667 | 1.353846 | 0.946548 |
| rdkit_SMR_VSA1 | 7.185607 | 18.186194 | -0.890605 |
| rdkit_Kappa3 | 1.950538 | 4.175638 | -0.863107 |
| rdkit_VSA_EState6 | 12.774518 | 6.303167 | 0.859318 |
| physchem_NumRotatableBonds | 1.536232 | 4.438462 | -0.840981 |
| rdkit_NumRotatableBonds | 1.536232 | 4.438462 | -0.840981 |
| rdkit_fr_bicyclic | 2.550725 | 0.853846 | 0.830704 |
| rdkit_MinEStateIndex | -0.154070 | -1.148410 | 0.811848 |
| rdkit_NumAromaticCarbocycles | 2.231884 | 1.084615 | 0.807978 |

## false negative vs true positive descriptor profile

| Descriptor | Left mean | Right mean | SMD |
|---|---:|---:|---:|
| rdkit_MaxAbsPartialCharge | 0.407344 | 0.323077 | 0.686338 |
| rdkit_fr_nitroso | 0.064516 | 0.312883 | -0.669382 |
| rdkit_MinPartialCharge | -0.399420 | -0.320284 | -0.635562 |
| rdkit_SMR_VSA5 | 29.556424 | 14.249318 | 0.616220 |
| rdkit_SlogP_VSA3 | 9.304977 | 4.061155 | 0.598428 |
| rdkit_MinEStateIndex | -0.829236 | -0.090550 | -0.565449 |
| rdkit_NumSaturatedCarbocycles | 0.430108 | 0.049080 | 0.528830 |
| rdkit_PEOE_VSA14 | 4.183107 | 1.308334 | 0.527126 |
| rdkit_SMR_VSA1 | 14.875530 | 7.861809 | 0.511716 |
| rdkit_MaxPartialCharge | 0.233153 | 0.169726 | 0.510786 |

这些差异是描述性 error-profile 信号，不构成因果解释或 v1 修改依据。
