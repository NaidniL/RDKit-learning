# Trustworthy RDKit-based Toxicity Modeling Workflow

## Purpose

This document abstracts the carcinogenicity project into a reusable workflow for a new toxicity endpoint. It records reusable software and control contracts; it does not allow an endpoint to reuse v1 labels, thresholds, final artifacts, or external results.

## Workflow map

| Module | Existing implementation | Reusable contract | Must be renewed for a new endpoint |
|---|---|---|---|
| Data audit | `src/carcinogenicity/cleaning.py`, `scripts/clean_datasets.py` | Keep source-record provenance, log exclusions, preserve manual-review evidence, and write auditable artifacts. | Source adapters, endpoint-specific label ontology, review decisions, and source policies. |
| Label resolution | Cleaning policies and formal dataset assembly | Resolve labels before splitting; preserve conflict/uncertainty states rather than silently coercing them. | Endpoint-specific positive/negative definitions and resolution precedence. |
| Structure standardization | `src/modeling_dataset/compounds.py`, `structure_algorithms.py` | Canonicalize structures deterministically; retain identifiers and standardization checks. | Any endpoint-specific salt, tautomer, mixture, or inorganic-structure policy. |
| Leakage-safe split | `src/modeling_dataset/splits.py`, `structure_relations.py` | Construct train, validation, CV, scaffold, nearest-neighbor, and overlap artifacts before model development. | Split seed, grouping rule, development/external membership, and leakage acceptance criteria. |
| Formal release | `manifests.py`, `dataset_release_reader.py` | Train only through a canonical pointer, manifest metadata, schema validation, and artifact hashes. | New release ID, manifest, schemas, and hashes. |
| Feature registry | `src/modeling/feature_registry.py`, `featurizers.py` | Features are derived only from approved structure columns; source, label, ID, and audit fields remain prohibited. | New feature versions or newly admitted feature groups, each preregistered. |
| Model registry | `experiment_config.py`, `train_baseline.py` | Serialize model family, parameters, seed, preprocessing, CV protocol, and metric. | Candidate families, grids, selection hierarchy, and calibration policy. |
| External lock | `evaluation_guard.py`, `external_final.py` | External data is denied during development; final evaluation requires an explicit frozen artifact and a repeat lock. | New external split, unlock record, final evaluation manifest, and archival tag. |
| Applicability domain | `reports.py`, `report_v2_validation_applicability_domain.py` | Quantify structural support with fixed fingerprint/similarity definitions and report strata without concealing low-support cases. | Bins, domain threshold, abstention policy, and validation plan frozen before final evaluation. |
| Uncertainty / inconclusive output | `consensus_v2_development_v1.json`, consensus reports | Treat disagreement and low support as reportable outcomes; measure coverage and selective performance. | Consensus members, decision rule, coverage target, and error-interception metric. |
| Interpretability report | `report_v1_descriptor_shap.py`, chemical-hypothesis memo | Separate attribution, chemical hypotheses, and causal claims; preserve model/artifact provenance. | Explanation population, background set, plots, case-selection rule, and hypothesis-validation plan. |

## Endpoint lifecycle

```text
source inventory
  -> auditable cleaning and label resolution
  -> formal release + leakage audit
  -> development-only candidate experiments
  -> frozen selection and final refit artifact
  -> independent audit
  -> one-shot final evaluation
  -> post hoc diagnostics without feedback into the frozen model
```

Each arrow produces a versioned artifact with a hash or manifest reference. A downstream result cannot retroactively alter an upstream decision; a new decision starts a new version.

## Non-negotiable controls

1. Never use source identity, label, review, ID, split, or leakage columns as features.
2. Do not use external data for feature selection, tuning, calibration, threshold setting, or candidate selection.
3. Freeze a final artifact before final evaluation; keep model and preprocessing artifacts separate and hashed.
4. Make external evaluation one-shot unless a separately reviewed protocol explicitly permits more than one analysis.
5. Report uncertainty, coverage, and applicability domain alongside discrimination metrics when the workflow is used for screening.
6. Treat SHAP, feature importance, similarity, and scaffold analyses as descriptive unless independently validated as causal or mechanistic evidence.

## v1/v2 status

Carcinogenicity v1 is the reference frozen baseline. The v2 consensus, disagreement, and validation applicability-domain reports are development-only research artifacts. They do not create a v2 final model or authorize another use of the v1 primary external split.
