"""构建清洗后的致癌性开发集和外部测试集。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcinogenicity.cleaning import CleaningConfig, run_cleaning  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="构建可审计的致癌性建模数据集")
    parser.add_argument(
        "--split-method",
        choices=["random", "scaffold", "none"],
        default="random",
        help="使用 random 复刻论文的标签分层 80:20 划分；scaffold 使用骨架划分",
    )
    parser.add_argument(
        "--validation-size", type=float, default=0.20, help="验证集比例"
    )
    parser.add_argument("--random-seed", type=int, default=42, help="随机种子")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "生成 reports/cleaning/audits/<run-id> 审计报告和完整拟输出，"
            "不写入 processed 数据"
        ),
    )
    parser.add_argument(
        "--approved-audit-run",
        default="",
        help="正式运行必填：已人工审核的 dry-run 批次 ID",
    )
    args = parser.parse_args()
    if not 0 < args.validation_size < 1:
        parser.error("--validation-size 必须大于 0 且小于 1")
    if not args.dry_run and not args.approved_audit_run.strip():
        parser.error("正式运行必须指定 --approved-audit-run")
    run_cleaning(
        CleaningConfig(
            root=ROOT,
            split_method=args.split_method,
            validation_size=args.validation_size,
            random_seed=args.random_seed,
            dry_run=args.dry_run,
            approved_audit_run=args.approved_audit_run.strip(),
        )
    )


if __name__ == "__main__":
    main()
