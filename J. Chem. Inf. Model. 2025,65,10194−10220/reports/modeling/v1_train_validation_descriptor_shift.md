# v1 train-validation descriptor distribution diagnostic

状态：`POST HOC, MODEL FROZEN`。

本报告仅比较 formal release 中的 train 与 fixed validation descriptor 分布。它不读取 external，不改变已冻结模型、预处理或 threshold；标准化均值差（SMD）是描述性统计，不用于 v1 选择或调参。

## Locked inputs

- final training manifest SHA-256: `8bd0f85e8f5a8309f534beb2247f4513fb656dfd374fdbcb50b164aabaaa3f5b`
- dataset release: `20260711_194149_961442_UTC_formal_e20e3008`
- dataset manifest SHA-256: `b04e0841cb0bdf5096f6961c7d2f07287649972fcd6b1b6b391badf6dcb2e4f2`
- train samples: `736`
- validation samples: `185`
- descriptors compared: `220`

## Largest absolute standardized mean differences

| Rank | Descriptor | Train mean | Validation mean | SMD (validation - train) | Train missing | Validation missing |
|---:|---|---:|---:|---:|---:|---:|
| 1 | rdkit_EState_VSA8 | 11.664898 | 8.833480 | -0.191742 | 0.0000 | 0.0000 |
| 2 | rdkit_VSA_EState2 | 10.935559 | 13.651506 | 0.178340 | 0.0000 | 0.0000 |
| 3 | rdkit_MinAbsPartialCharge | 0.212873 | 0.231745 | 0.166462 | 0.0082 | 0.0108 |
| 4 | rdkit_fr_C_O | 0.574728 | 0.745946 | 0.156828 | 0.0000 | 0.0000 |
| 5 | rdkit_fr_COO2 | 0.096467 | 0.156757 | 0.148958 | 0.0000 | 0.0000 |
| 6 | rdkit_fr_COO | 0.096467 | 0.156757 | 0.148958 | 0.0000 | 0.0000 |
| 7 | rdkit_fr_ketone | 0.088315 | 0.162162 | 0.146829 | 0.0000 | 0.0000 |
| 8 | rdkit_MaxPartialCharge | 0.221694 | 0.239954 | 0.146533 | 0.0082 | 0.0108 |
| 9 | rdkit_VSA_EState1 | 8.722316 | 6.136934 | -0.146511 | 0.0000 | 0.0000 |
| 10 | rdkit_SMR_VSA4 | 3.635246 | 4.676208 | 0.140098 | 0.0000 | 0.0000 |
| 11 | rdkit_MaxEStateIndex | 9.455900 | 9.820410 | 0.135398 | 0.0000 | 0.0000 |
| 12 | rdkit_MaxAbsEStateIndex | 9.455900 | 9.820410 | 0.135398 | 0.0000 | 0.0000 |
| 13 | rdkit_fr_methoxy | 0.119565 | 0.064865 | -0.134368 | 0.0000 | 0.0000 |
| 14 | rdkit_fr_thiazole | 0.029891 | 0.010811 | -0.131031 | 0.0000 | 0.0000 |
| 15 | rdkit_fr_imide | 0.008152 | 0.000000 | -0.128212 | 0.0000 | 0.0000 |
| 16 | rdkit_SlogP_VSA4 | 4.656088 | 5.769805 | 0.127389 | 0.0000 | 0.0000 |
| 17 | rdkit_SlogP_VSA8 | 2.928953 | 2.213403 | -0.122905 | 0.0000 | 0.0000 |
| 18 | rdkit_fr_unbrch_alkane | 0.313859 | 0.156757 | -0.122583 | 0.0000 | 0.0000 |
| 19 | rdkit_fr_isothiocyan | 0.001359 | 0.010811 | 0.121769 | 0.0000 | 0.0000 |
| 20 | rdkit_fr_Al_COO | 0.074728 | 0.118919 | 0.120567 | 0.0000 | 0.0000 |

## Boundary

- This is not a train-vs-external shift report: primary external remains one-shot locked and its sample-level predictions were not retained.
- Any v2 distributional or domain policy must be frozen before a separately authorized final evaluation.
