# v1 diagnostic scope audit

状态：`POST HOC DIAGNOSTICS CONSTRAINED BY FINAL EXTERNAL LOCK`。

## Purpose

This audit defines which research diagnostics can be performed without changing, re-evaluating, or treating the frozen v1 primary external result as development feedback. It is a scope record, not a model-development artifact.

## Frozen v1 evidence

- Final model summary: `reports/modeling/final_model_v1_summary.md`.
- Final artifact audit: `reports/modeling/final_artifact_independent_audit.md` (`PASS`).
- One-shot external evaluation audit: `reports/modeling/final_external_evaluation_audit.md` (`PASS`).
- Primary external result: `455` samples, threshold `0.5`, AUROC `0.719437`, AUPRC `0.772798`, MCC `0.287757`.
- The external evaluation manifest contains an aggregate metric record and a canonical prediction digest, with `artifact_written=false`; it does not retain per-sample predictions.

## Permitted post hoc work now

| Diagnostic | Permitted evidence | Status |
|---|---|---|
| Validation vs external aggregate comparison | Frozen validation and external aggregate reports | Available; descriptive only |
| Descriptor global SHAP | Frozen model + train/validation only | Completed in `reports/modeling/v1_descriptor_shap.md` |
| Descriptor train vs validation distribution comparison | Formal release train/validation CSV only | Permitted |
| Validation error / scaffold / nearest-neighbor analysis | Formal release train/validation CSV and frozen model | Permitted |
| Methodology design for applicability domain and consensus v2 | Documentation and development-only protocol | Permitted |

## Not permitted for v1

| Requested analysis | Why it is not performed now |
|---|---|
| Recompute primary external predictions | The primary external evaluation is one-shot locked and repeat execution is rejected. |
| External false-positive / false-negative case table | No per-sample external predictions were written; regenerating them would re-read the locked primary external split. |
| External similarity/scaffold stratified AUROC or MCC | It requires the unavailable per-sample external predictions and would constitute a repeat external analysis. |
| Change model, feature set, preprocessing, grid, calibration, or threshold | Any such use of the external result would invalidate v1’s frozen-selection and one-shot-evaluation design. |

## Consequence for v2

The next model-development cycle must use development data only to predefine candidate representations, an applicability-domain rule, and an inconclusive policy. If a future final evaluation is authorized, it requires a separately frozen v2 artifact and a separately documented external-evaluation protocol. The locked v1 primary external result remains a baseline endpoint and must not be used to tune that design.
