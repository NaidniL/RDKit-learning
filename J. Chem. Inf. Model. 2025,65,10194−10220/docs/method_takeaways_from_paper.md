# Method takeaways from the reference paper

## Purpose

This note records methods that are transferable from Huynh Anh Duy and Tarapong Srisongkram, *Toward Explainable Carcinogenicity Prediction: An Integrated Cheminformatics Approach and Consensus Framework for Possibly Carcinogenic Chemicals*, J. Chem. Inf. Model. 2025, 65, 10194-10220. It is a v2 research-design note, not a claim that those analyses have already been performed in this repository.

The v1 model, release, threshold, and one-shot primary external result remain frozen. Nothing in this note authorizes using the v1 external result for model selection, hyperparameter tuning, feature changes, or threshold changes.

## Complementary representations

The paper combines three learners built from distinct molecular views: MACCS fingerprints, RDKit descriptors, and E-state features. The transferable idea is not the exact architectures; it is to test whether models that encode different chemical information make complementary errors.

For this repository, a development-only v2 comparison can use the already defined views:

- LightGBM + RDKit/physicochemical descriptors;
- RF or LightGBM + MACCS;
- an ECFP-based learner or nearest-neighbor reference.

The question is whether their agreement, disagreement, and error overlap can identify predictions that deserve less confidence. Any candidate selection and policy design must use development data only; the frozen v1 primary external result remains a historical endpoint, not feedback.

## Consensus as uncertainty handling

The paper uses unanimity at a fixed probability threshold to emit carcinogen or noncarcinogen; discordant model outputs are retained as **inconclusive**. This is a useful decision-design principle: abstention can be an informative output rather than a forced error-prone binary call.

For a future v2 policy, define the rule before final evaluation and report both:

- **coverage**: fraction of compounds receiving a positive or negative call;
- **selective performance**: AUROC, MCC, and accuracy on the covered subset;
- **inconclusive rate** and the fraction of observed errors intercepted by abstention.

Probability proximity to 0.5, model disagreement, nearest-neighbor label conflict, and out-of-domain status are candidate inputs to this policy. They are hypotheses for development-only evaluation, not retrospectively optimized rules for v1.

## Applicability domain

The paper explicitly characterizes applicability domain with k-nearest-neighbor distances in molecular fingerprint space, separating within-domain and out-of-domain compounds before making deployment-oriented calls. The transferable implementation is to make structural support visible for every prediction.

This project already has leakage, nearest-neighbor, scaffold, and tautomer-sensitivity foundations. A v2 domain report should therefore predefine and expose categories such as:

- in-domain / near-domain / low-similarity;
- scaffold-seen / scaffold-novel;
- nearest-neighbor label agreement / conflict.

For the locked v1 result, these can be post hoc descriptive strata only. They must not change its model, features, threshold, or reported aggregate result.

## SHAP and scaffold interpretation

The paper uses SHAP to connect predictive features to MACCS substructures and Bemis-Murcko scaffolds. The transferable lesson is to translate attribution into chemically inspectable questions, rather than treating a feature-importance plot as an endpoint.

Because v1 is LightGBM + descriptors, its appropriate explanation workflow is:

1. global LightGBM feature importance and SHAP summary;
2. directional descriptor effects and dependence plots;
3. descriptor distributions by split and by correct/incorrect prediction strata;
4. scaffold and nearest-neighbor context for selected cases.

Interpretations should distinguish association in the training data from mechanistic causation. Post hoc external error analysis is allowed as diagnosis, but it cannot be used to revise v1.

## Deployment-oriented workflow

The paper’s consensus workflow combines standardization, serialized models, domain checks, confidence-aware output, and a practical prediction interface. The transferable system design for this repository is:

```text
data audit -> label resolution -> structure standardization -> leakage-safe split
-> feature/model registry -> frozen final artifact -> external lock
-> domain and uncertainty assessment -> interpretable screening output
```

The target is a trustworthy RDKit-based toxicity-modeling workflow that can later be adapted to other endpoints. Each new endpoint or v2 model family requires a new data release, development-only design, independent audit, and separately authorized final evaluation.
