"""阶段 2 建模数据集组装入口（实现批次 3）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling_dataset.fingerprint import input_fingerprint  # noqa: E402
from modeling_dataset.core_pipeline import validate_core  # noqa: E402
from modeling_dataset.schema_registry import (  # noqa: E402
    ARTIFACT_SCHEMAS,
    validate_registry,
)
from modeling_dataset.serialization import canonical_json  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="阶段 2 可审计建模数据集组装")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-inputs", help="只读验证冻结输入并计算指纹")
    subparsers.add_parser("validate-core", help="纯内存重建来源、结构与角色")
    audit = subparsers.add_parser("audit", help="生成 assembly dry-run 审计")
    audit.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="仅生成审计候选（后续批次尚未解锁）",
    )
    formal = subparsers.add_parser("formal", help="生成正式 release")
    formal.add_argument(
        "--approved-audit-run",
        required=True,
        help="已批准的 assembly audit run-id",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-inputs":
        validate_registry()
        fingerprint, descriptor = input_fingerprint(
            ROOT,
            parameters={
                "implementation_batch": 3,
                "schema_count": len(ARTIFACT_SCHEMAS),
            },
        )
        print(
            canonical_json(
                {
                    "input_fingerprint": fingerprint,
                    "manual_conflict_file": descriptor["manual_conflict_file"][
                        "state"
                    ],
                    "policy_sha256": descriptor["policy"]["sha256"],
                    "processed_file_count": len(descriptor["processed_files"]),
                    "schema_count": len(ARTIFACT_SCHEMAS),
                    "status": "validated",
                }
            )
        )
        return 0
    if args.command == "validate-core":
        validate_registry()
        result = validate_core(ROOT)
        print(canonical_json(result.summary))
        return 0
    if args.command == "audit":
        print(
            "split 与发布报告尚未实现；批次 3 不会创建 assembly audit 目录。",
            file=sys.stderr,
        )
        return 2
    if args.command == "formal":
        print(
            "正式 release 被硬性拒绝：尚未完成业务组装、人工审核和最终 audit 批准。",
            file=sys.stderr,
        )
        return 2
    raise AssertionError("argparse 返回了未知命令")


if __name__ == "__main__":
    raise SystemExit(main())
