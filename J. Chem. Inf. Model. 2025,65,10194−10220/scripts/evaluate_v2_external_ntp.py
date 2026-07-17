#!/usr/bin/env python3
"""Run the user-authorized, one-shot v2 evaluation on the frozen NTP candidate."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from modeling.dataset_release_reader import load_formal_release_metadata_without_external_reads  # noqa: E402
from modeling.external_final import sha256_json_rows  # noqa: E402
from modeling.featurizers import featurize_smiles  # noqa: E402
from modeling.metrics import binary_confusion_counts, binary_metrics  # noqa: E402
from modeling.selective_prediction import hard_predictions, v2_output_records  # noqa: E402
from modeling.split_loader import load_train_validation_splits  # noqa: E402
from modeling.train_baseline import predict_probability  # noqa: E402
from modeling.v2_final_artifact import sha256_file, validate_artifact_hashes  # noqa: E402
from modeling.v2_final_policy import load_v2_final_policy  # noqa: E402
from modeling_dataset.serialization import canonical_json_bytes  # noqa: E402
from modeling_dataset.structure_algorithms import murcko_scaffold, parse_parent, tautomer_family_key  # noqa: E402


AUTHORIZATION_PATH = ROOT / "configs" / "v2_external_evaluation_ntp_authorization_v1.json"
CANDIDATE_MANIFEST_PATH = ROOT / "data" / "interim" / "v2_external_ntp_candidate_release_manifest.json"
CANDIDATE_PATH = ROOT / "data" / "processed" / "v2_external_ntp_candidate.csv"
ARTIFACT_DIR = ROOT / "models" / "final_consensus_v2"
V1_ARTIFACT_DIR = ROOT / "models" / "final_model_v1"
EVALUATION_DIR = ROOT / "reports" / "modeling" / "v2_external_evaluation_v1"
EXPECTED_OUTPUTS = {"external_evaluation_manifest.json", "external_evaluation.md"}
MEMBERS = ("lightgbm_descriptors", "random_forest_maccs", "random_forest_ecfp4")


def load_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ValueError(f"{path.name} 必须是 canonical JSON object")
    return value


def transform(preprocessing: Any, values: Any) -> Any:
    return values if preprocessing == "passthrough" else preprocessing.transform(values)


def maximum_tanimoto(train: sparse.csr_matrix, query: sparse.csr_matrix) -> np.ndarray:
    intersections = query @ train.T
    train_bits = np.asarray(train.sum(axis=1)).ravel()
    query_bits = np.asarray(query.sum(axis=1)).ravel()
    values = np.zeros(query.shape[0], dtype=float)
    for index in range(query.shape[0]):
        row = intersections.getrow(index)
        denominators = query_bits[index] + train_bits[row.indices] - row.data
        scores = np.divide(row.data, denominators, out=np.zeros_like(row.data, dtype=float), where=denominators > 0)
        values[index] = float(scores.max()) if len(scores) else 0.0
    return values


def metric_summary(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any] | None:
    if not len(truth):
        return None
    return {"confusion": binary_confusion_counts(truth, prediction), "metrics": binary_metrics(truth, prediction)}


def stratum_summary(
    masks: list[tuple[str, np.ndarray]], truth: np.ndarray, covered: np.ndarray, consensus: np.ndarray
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name, mask in masks:
        selected = np.flatnonzero(mask)
        selected_covered = selected[covered[selected]]
        output.append(
            {
                "stratum": name,
                "sample_count": int(len(selected)),
                "covered_count": int(len(selected_covered)),
                "coverage": float(len(selected_covered) / len(selected)) if len(selected) else None,
                "covered_metrics": metric_summary(truth[selected_covered], consensus[selected_covered]),
            }
        )
    return output


def format_metrics(summary: dict[str, Any] | None) -> tuple[str, str, str, str, str, str]:
    if summary is None:
        return ("null",) * 6
    metric, confusion = summary["metrics"], summary["confusion"]
    return (
        f"{metric['mcc']:.6f}", f"{metric['accuracy']:.6f}", f"{metric['sensitivity']:.6f}",
        f"{metric['specificity']:.6f}",
        f"{confusion['true_negative']} / {confusion['false_positive']} / {confusion['false_negative']} / {confusion['true_positive']}",
        str(summary["metrics"]["auroc"] if summary["metrics"]["auroc"] is not None else "null"),
    )


def markdown(manifest: Mapping[str, Any]) -> str:
    summary = manifest["summary"]
    lines = ["# v2 one-shot NTP external evaluation", "", "状态：`COMPLETE`。", "", "此报告是用户授权的唯一一次 NTP candidate external evaluation。未读取 v1 CCRIS external；没有改变 policy、成员、预处理、阈值或 AD call。仅保留聚合统计和 prediction digest，不写样本级 prediction artifact。", "", "## Calls and coverage", "", "| Total | Carcinogen calls | Noncarcinogen calls | Inconclusive | Coverage | Carcinogen coverage | Noncarcinogen coverage |", "|---:|---:|---:|---:|---:|---:|---:|", f"| {summary['sample_count']} | {summary['call_counts']['carcinogen']} | {summary['call_counts']['noncarcinogen']} | {summary['call_counts']['inconclusive']} | {summary['coverage']:.6f} | {summary['class_conditional_coverage']['carcinogen']:.6f} | {summary['class_conditional_coverage']['noncarcinogen']:.6f} |", "", "## Same-covered-subset comparison", "", "| Model | Population | n | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for name, value in [("v2 consensus", summary["consensus_covered"]), *[(key, item["covered"]) for key, item in manifest["members"].items()]]:
        mcc, accuracy, sensitivity, specificity, confusion, _ = format_metrics(value)
        lines.append(f"| {name} | v2 covered subset | {value['sample_count'] if value else 0} | {mcc} | {accuracy} | {sensitivity} | {specificity} | {confusion} |")
    lines.extend(["", "## Member full-external performance", "", "| Member | n | MCC | Accuracy | Sensitivity | Specificity | TN / FP / FN / TP |", "|---|---:|---:|---:|---:|---:|---|"])
    for name, item in manifest["members"].items():
        mcc, accuracy, sensitivity, specificity, confusion, _ = format_metrics(item["full"])
        lines.append(f"| {name} | {item['full']['sample_count']} | {mcc} | {accuracy} | {sensitivity} | {specificity} | {confusion} |")
    lines.extend(["", "## Error interception", "", f"- mean member error rate, covered / inconclusive: `{summary['member_error_rates']['covered_mean']:.6f}` / `{summary['member_error_rates']['inconclusive_mean']:.6f}`", f"- member error events in rejected subset: `{summary['member_error_rates']['inconclusive_error_events']}` of `{summary['member_error_rates']['total_error_events']}` (`{summary['member_error_rates']['inconclusive_error_event_fraction']:.6f}`)", f"- any-member-wrong rate, covered / inconclusive: `{summary['member_error_rates']['covered_any_error_rate']:.6f}` / `{summary['member_error_rates']['inconclusive_any_error_rate']:.6f}`", "", "## AD and scaffold strata", "", "| Stratum | n | Covered | Coverage | Covered MCC |", "|---|---:|---:|---:|---:|"])
    for item in [*manifest["similarity_strata"], *manifest["scaffold_strata"]]:
        covered_metrics = item["covered_metrics"]
        value = "null" if covered_metrics is None else f"{covered_metrics['metrics']['mcc']:.6f}"
        coverage = "null" if item["coverage"] is None else f"{item['coverage']:.6f}"
        lines.append(f"| {item['stratum']} | {item['sample_count']} | {item['covered_count']} | {coverage} | {value} |")
    lines.extend(["", "## Frozen success-criterion readout", "", f"- coverage ≥ 0.65: `{manifest['success_criteria']['coverage_minimum_met']}`", f"- covered sensitivity / specificity ≥ 0.65: `{manifest['success_criteria']['covered_sensitivity_minimum_met']}` / `{manifest['success_criteria']['covered_specificity_minimum_met']}`", f"- inconclusive mean member error rate > covered: `{manifest['success_criteria']['inconclusive_error_enriched']}`", f"- v2 MCC ≥ v1 MCC on same v2 covered subset: `{manifest['v1_same_covered_subset']['requirement_met']}` (v2 `{manifest['v1_same_covered_subset']['v2_mcc']:.6f}`, v1 `{manifest['v1_same_covered_subset']['v1_mcc']:.6f}`)", "", "Tautomer diagnostic：所有 candidate 在 candidate-construction overlap audit 中均与 development tautomer family 零重叠；本次仅描述该边界，不改变输入结构或 call。", ""])
    return "\n".join(lines)


def main() -> int:
    authorization = load_canonical_json(AUTHORIZATION_PATH)
    candidate_manifest = load_canonical_json(CANDIDATE_MANIFEST_PATH)
    policy, policy_sha = load_v2_final_policy(ROOT / "configs" / "v2_final_policy_v1.json")
    expected_auth = {"authorization_id", "candidate_release_manifest", "execution", "final_artifact", "policy", "status", "v1_primary_external", "version"}
    if set(authorization) != expected_auth or authorization["status"] != "FROZEN_ONE_SHOT_EXTERNAL_EVALUATION_AUTHORIZED":
        raise PermissionError("external authorization 不完整或未冻结")
    if EVALUATION_DIR.exists():
        raise FileExistsError("v2 external evaluation output 已存在；拒绝再次读取 candidate")
    if authorization["v1_primary_external"] != "prohibited" or authorization["execution"] != {"output_directory": "reports/modeling/v2_external_evaluation_v1", "prediction_csv_prohibited": True, "repeat_execution_prohibited": True, "single_external_read": True}:
        raise PermissionError("authorization 不允许一次性 NTP evaluation")
    if authorization["policy"] != {"sha256": policy_sha, "status": "FROZEN_FINAL_POLICY_PRE_EXTERNAL"}:
        raise ValueError("authorization 与 frozen policy 不一致")
    if authorization["candidate_release_manifest"] != {"path": "data/interim/v2_external_ntp_candidate_release_manifest.json", "sha256": sha256_file(CANDIDATE_MANIFEST_PATH)}:
        raise ValueError("authorization 与 candidate release manifest 不一致")
    if candidate_manifest.get("status") != "FROZEN_CANDIDATE_PRE_EXTERNAL_AUTHORIZATION" or candidate_manifest.get("external_evaluation_authorized") is not False:
        raise PermissionError("candidate release manifest 不满足授权前状态")
    if candidate_manifest.get("candidate_csv", {}).get("sha256") != sha256_file(CANDIDATE_PATH):
        raise ValueError("candidate CSV hash 与 manifest 不一致")
    if authorization["final_artifact"] != {"artifact_hashes_sha256": sha256_file(ARTIFACT_DIR / "artifact_hashes.json"), "training_manifest_sha256": sha256_file(ARTIFACT_DIR / "training_manifest.json")}:
        raise ValueError("authorization 与 final artifact 不一致")
    validate_artifact_hashes(ARTIFACT_DIR, load_canonical_json(ARTIFACT_DIR / "artifact_hashes.json"))
    if sha256_file(ARTIFACT_DIR / "v2_final_policy.json") != policy_sha:
        raise ValueError("final artifact 内 policy hash 不一致")

    # This directory creation is the irreversible one-shot lock and precedes opening candidate rows.
    EVALUATION_DIR.mkdir(parents=True)
    try:
        with CANDIDATE_PATH.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        required = {"candidate_id", "canonical_smiles", "connectivity_key", "normalized_label", "standardized_inchikey", "tautomer_family_key"}
        if not rows or not required <= set(rows[0]) or len(rows) != candidate_manifest["candidate_rows"]:
            raise ValueError("candidate rows 不符合 frozen release manifest")
        truth = np.asarray([int(row["normalized_label"]) for row in rows])
        release = load_formal_release_metadata_without_external_reads(ROOT / "releases" / "dataset_assembly")
        splits = load_train_validation_splits(release)
        development = [*splits.train, *splits.validation]
        exact = {str(row["standardized_inchikey"]) for row in development}
        connectivity = {item.split("-")[0] for item in exact}
        tautomers = {tautomer_family_key(parse_parent(str(row["canonical_smiles"]))) for row in development}
        overlap = {"exact_overlap_count": len({row["standardized_inchikey"] for row in rows} & exact), "connectivity_overlap_count": len({row["connectivity_key"] for row in rows} & connectivity), "tautomer_overlap_count": len({row["tautomer_family_key"] for row in rows} & tautomers)}
        if any(overlap.values()):
            raise ValueError("candidate 与 development overlap 不为零")
        smiles = [str(row["canonical_smiles"]) for row in rows]
        probabilities: list[np.ndarray] = []
        for spec in policy["members"]:
            member_id = str(spec["id"])
            matrix = featurize_smiles(smiles, tuple(spec["feature_sets"]))
            model = joblib.load(ARTIFACT_DIR / f"member_{member_id}_model.pkl")
            preprocessing = joblib.load(ARTIFACT_DIR / f"member_{member_id}_preprocessing.pkl")
            probabilities.append(predict_probability(model, transform(preprocessing, matrix.values)))
        probability_matrix = np.column_stack(probabilities)
        calls = hard_predictions(probability_matrix, threshold=0.5)
        outputs = v2_output_records(probability_matrix, threshold=0.5)
        covered = np.asarray([not bool(item["review_required"]) for item in outputs])
        consensus = calls[:, 0]
        member_error = calls != truth[:, None]
        covered_indices, inconclusive_indices = np.flatnonzero(covered), np.flatnonzero(~covered)
        consensus_covered = metric_summary(truth[covered_indices], consensus[covered_indices])
        members = {member_id: {"full": {"sample_count": len(truth), **metric_summary(truth, probability_matrix[:, index])}, "covered": {"sample_count": len(covered_indices), **metric_summary(truth[covered_indices], probability_matrix[covered_indices, index])}} for index, member_id in enumerate(MEMBERS)}
        ecfp_development = featurize_smiles((str(row["canonical_smiles"]) for row in development), ("ecfp4",)).values
        ecfp_external = featurize_smiles(smiles, ("ecfp4",)).values
        similarity = maximum_tanimoto(ecfp_development, ecfp_external)
        similarity_strata = stratum_summary([("AD similarity [0.85,1.00]", similarity >= .85), ("AD similarity [0.70,0.85)", (similarity >= .70) & (similarity < .85)), ("AD similarity [0.50,0.70)", (similarity >= .50) & (similarity < .70)), ("AD similarity [0.00,0.50)", similarity < .50)], truth, covered, consensus)
        dev_scaffolds = {murcko_scaffold(parse_parent(str(row["canonical_smiles"]))) for row in development} - {""}
        ext_scaffolds = np.asarray([murcko_scaffold(parse_parent(value)) for value in smiles], dtype=object)
        seen_scaffold = np.asarray([value != "" and value in dev_scaffolds for value in ext_scaffolds], dtype=bool)
        scaffold_strata = stratum_summary([("Scaffold seen in final-refit development", seen_scaffold), ("Scaffold novel to final-refit development", ~seen_scaffold)], truth, covered, consensus)
        descriptor = featurize_smiles(smiles, ("rdkit_descriptors", "physicochemical"))
        v1_training = load_canonical_json(V1_ARTIFACT_DIR / "training_manifest.json")
        if list(descriptor.feature_names) != v1_training["descriptor_list"]:
            raise ValueError("v1 descriptor layout 不一致")
        v1_model, v1_preprocess = joblib.load(V1_ARTIFACT_DIR / "model.pkl"), joblib.load(V1_ARTIFACT_DIR / "preprocessing.pkl")
        v1_probability = predict_probability(v1_model, transform(v1_preprocess, descriptor.values))
        v1_same = metric_summary(truth[covered_indices], v1_probability[covered_indices])
        digest_rows = [{"candidate_id": row["candidate_id"], "label": int(label), "member_probabilities": [float(value) for value in probabilities_row], "output": output["prediction"]} for row, label, probabilities_row, output in zip(rows, truth, probability_matrix, outputs, strict=True)]
        error_events = int(member_error.sum())
        inconclusive_error_events = int(member_error[inconclusive_indices].sum())
        call_counter = Counter(item["prediction"] for item in outputs)
        summary = {"sample_count": len(truth), "class_counts": {"carcinogen": int((truth == 1).sum()), "noncarcinogen": int((truth == 0).sum())}, "call_counts": {"carcinogen": call_counter["carcinogen"], "noncarcinogen": call_counter["noncarcinogen"], "inconclusive": call_counter["inconclusive"]}, "coverage": float(covered.mean()), "class_conditional_coverage": {"carcinogen": float(covered[truth == 1].mean()), "noncarcinogen": float(covered[truth == 0].mean())}, "consensus_covered": {"sample_count": len(covered_indices), **consensus_covered}, "member_error_rates": {"covered_mean": float(member_error[covered_indices].mean()), "inconclusive_mean": float(member_error[inconclusive_indices].mean()), "total_error_events": error_events, "inconclusive_error_events": inconclusive_error_events, "inconclusive_error_event_fraction": float(inconclusive_error_events / error_events) if error_events else 0.0, "covered_any_error_rate": float(member_error[covered_indices].any(axis=1).mean()), "inconclusive_any_error_rate": float(member_error[inconclusive_indices].any(axis=1).mean())}}
        v1_same_record = {"v1_mcc": v1_same["metrics"]["mcc"], "v2_mcc": consensus_covered["metrics"]["mcc"], "requirement_met": bool(consensus_covered["metrics"]["mcc"] >= v1_same["metrics"]["mcc"]), "v1_training_manifest_sha256": sha256_file(V1_ARTIFACT_DIR / "training_manifest.json")}
        success = {"coverage_minimum_met": bool(summary["coverage"] >= .65), "covered_sensitivity_minimum_met": bool(consensus_covered["metrics"]["sensitivity"] >= .65), "covered_specificity_minimum_met": bool(consensus_covered["metrics"]["specificity"] >= .65), "inconclusive_error_enriched": bool(summary["member_error_rates"]["inconclusive_mean"] > summary["member_error_rates"]["covered_mean"])}
        manifest = {"external_evaluation_manifest_version": 1, "external_evaluation_id": "v2_ntp_one_shot_external_evaluation_v1", "authorization": {"authorization_config_sha256": sha256_file(AUTHORIZATION_PATH), "new_external_manifest_sha256": sha256_file(CANDIDATE_MANIFEST_PATH), "v2_final_policy_sha256": policy_sha}, "external_dataset": {"candidate_id": candidate_manifest["candidate_id"], "candidate_csv_sha256": candidate_manifest["candidate_csv"]["sha256"], "candidate_release_manifest_sha256": sha256_file(CANDIDATE_MANIFEST_PATH), "sample_count": len(rows)}, "output_directory_lock": {"created_before_external_read": True, "repeat_execution_prevented": True}, "overlap_audit": overlap, "final_artifact": {"artifact_hashes_sha256": sha256_file(ARTIFACT_DIR / "artifact_hashes.json"), "training_manifest_sha256": sha256_file(ARTIFACT_DIR / "training_manifest.json"), "v2_final_policy_sha256": policy_sha}, "applicability_domain_call_effect": "none", "preregistered_diagnostics": ["tautomer_sensitivity_descriptive", "scaffold_stratified_metrics", "ecfp4_similarity_stratified_metrics"], "prediction_digest": {"artifact_written": False, "sha256": sha256_json_rows(digest_rows)}, "external_prediction_digest": {"artifact_written": False, "sha256": sha256_json_rows(digest_rows)}, "summary": summary, "members": members, "similarity_strata": similarity_strata, "scaffold_strata": scaffold_strata, "tautomer_diagnostic": {"development_tautomer_overlap_count": 0, "method": "candidate prefilter rechecked before scoring"}, "v1_same_covered_subset": v1_same_record, "success_criteria": success, "post_evaluation_model_or_policy_change": False}
        temporary = Path(tempfile.mkdtemp(prefix=".v2_external_result.", dir=EVALUATION_DIR.parent))
        try:
            manifest_temp, markdown_temp = temporary / "external_evaluation_manifest.json", temporary / "external_evaluation.md"
            manifest_temp.write_bytes(canonical_json_bytes(manifest))
            markdown_temp.write_text(markdown(manifest), encoding="utf-8")
            os.replace(manifest_temp, EVALUATION_DIR / manifest_temp.name)
            os.replace(markdown_temp, EVALUATION_DIR / markdown_temp.name)
        finally:
            temporary.rmdir()
    except Exception:
        raise
    print(json.dumps({"sample_count": len(rows), "coverage": summary["coverage"], "output_dir": str(EVALUATION_DIR)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
