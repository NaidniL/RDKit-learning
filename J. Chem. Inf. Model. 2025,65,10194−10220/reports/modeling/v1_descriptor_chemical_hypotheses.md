# v1 descriptor chemical hypotheses

状态：`POST HOC, HYPOTHESIS GENERATING`。

本备忘基于 `v1_descriptor_shap.md` 的冻结 train+validation 全局 SHAP 排名。它将 descriptor 名称转译为可检查的化学性质假设；它不主张因果关系，不包含 external 样本级分析，也不授权改变 v1。

## Observed attribution signals

| SHAP-ranked descriptor family | Chemical interpretation for follow-up | Boundary |
|---|---|---|
| `rdkit_fr_nitroso` | Nitroso functional-group presence was the largest mean absolute attribution in the frozen refit data. This makes nitroso-containing structures a candidate subgroup for descriptive review. | A fragment count can proxy correlated structure classes; it does not establish that a nitroso group causes the observed label. |
| `rdkit_PEOE_VSA5`, `rdkit_VSA_EState8`, `rdkit_VSA_EState5`, `rdkit_SMR_VSA4` | Partial-charge, E-state, and molar-refractivity surface-area bins indicate that electronic and surface-property patterns contributed to the fitted decision function. | Individual VSA bins are composite descriptors and should not be interpreted as isolated molecular mechanisms. |
| `rdkit_BertzCT`, `rdkit_Kappa3`, `rdkit_BalabanJ`, `rdkit_AvgIpc` | Graph-complexity, shape, and topological-index descriptors suggest that molecular architecture is represented in the model. | These indices can correlate with size, ring systems, and other features simultaneously. |
| `rdkit_SlogP_VSA3`, `rdkit_SlogP_VSA6`, `rdkit_SlogP_VSA8` | Lipophilicity-weighted surface-area features motivate a follow-up question about hydrophobic surface distribution. | The v1 SHAP ranking alone does not support a monotonic lipophilicity claim. |
| `rdkit_BCUT2D_*`, partial-charge extrema | BCUT and charge descriptors motivate a follow-up question about electronic distribution and polarizability. | Correlation among descriptors means their attributions should be interpreted jointly. |
| `rdkit_qed`, `rdkit_FpDensityMorgan2` | Drug-likeness and structural-density summaries appear in the global ranking and may capture broad chemical-space differences. | They are summary descriptors, not mechanistic endpoints. |

## Testable follow-up questions

The following are development-only questions for a separately preregistered v2 analysis:

1. Are high-attribution descriptor ranges associated with consistent within-development prediction behavior after controlling for correlated descriptors?
2. Do nitroso-bearing, high-complexity, or particular lipophilic-surface subgroups have different validation error rates?
3. Do scaffold-seen and scaffold-novel development compounds differ in descriptor profiles and model agreement?
4. Are high model-disagreement cases enriched for descriptor combinations that are sparse in the training distribution?

## Prohibited inference

These hypotheses cannot be used to change the frozen v1 feature set, LightGBM parameters, preprocessing, or threshold. They also cannot justify re-reading primary external data. A v2 final evaluation requires a new frozen artifact and separately authorized evaluation protocol.
