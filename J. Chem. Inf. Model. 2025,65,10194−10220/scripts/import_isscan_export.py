"""将 OECD QSAR Toolbox 导出的 ISSCAN 数据导入 data/raw/isscan_raw.csv。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd
from rdkit import Chem


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ARCHIVE = RAW / "source_archives" / "isscan"


def read_sdf(path: Path) -> pd.DataFrame:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
    rows: list[dict[str, object]] = []
    for index, molecule in enumerate(supplier, start=1):
        if molecule is None:
            raise ValueError(f"第 {index} 条 SDF 记录无效")
        row: dict[str, object] = dict(molecule.GetPropsAsDict(includePrivate=False))
        row["molblock_smiles"] = Chem.MolToSmiles(molecule, canonical=False)
        rows.append(row)
    return pd.DataFrame(rows)


def read_export(path: Path, sheet: str | int | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if suffix in {".xls", ".xlsx"}:
        selected_sheet: str | int = 0 if sheet is None else sheet
        return pd.read_excel(path, sheet_name=selected_sheet, dtype=str).fillna("")
    if suffix in {".sdf", ".sd"}:
        return read_sdf(path)
    raise ValueError("支持的输入格式为：.csv、.xls、.xlsx、.sdf、.sd")


def parse_sheet(value: str | None) -> str | int | None:
    if value is None:
        return None
    return int(value) if value.isdigit() else value


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 Toolbox ISSCAN 导出数据")
    parser.add_argument("export", type=Path, help="Toolbox ISSCAN 导出文件")
    parser.add_argument("--sheet", help="Excel 工作表名称或从 0 开始的索引")
    parser.add_argument(
        "--chemical-id-column",
        help="用于校验长表导出文件中唯一化学物数量的字段",
    )
    parser.add_argument("--expected-chemicals", type=int, default=1148)
    parser.add_argument(
        "--expected-rows",
        type=int,
        help="可选：对已知 Toolbox 导出布局执行精确行数校验",
    )
    args = parser.parse_args()

    source = args.export.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到导出文件：{source}")

    frame = read_export(source, parse_sheet(args.sheet)).dropna(how="all")
    frame.columns = [str(column).strip() for column in frame.columns]
    if args.expected_rows is not None and len(frame) != args.expected_rows:
        raise ValueError(
            f"预期 {args.expected_rows:,} 行，实际为 {len(frame):,} 行。"
        )

    if args.chemical_id_column:
        if args.chemical_id_column not in frame.columns:
            raise ValueError(
                f"找不到化学物 ID 字段 {args.chemical_id_column!r}。"
                f"可用字段：{', '.join(frame.columns)}"
            )
        chemical_count = frame[args.chemical_id_column].replace("", pd.NA).nunique()
    else:
        chemical_count = len(frame)

    if chemical_count != args.expected_chemicals:
        hint = (
            " 如果使用长表导出格式，请通过 --chemical-id-column "
            "指定化学物标识字段。"
            if args.chemical_id_column is None
            else ""
        )
        raise ValueError(
            f"预期 {args.expected_chemicals:,} 个 ISSCAN 化学物，"
            f"实际为 {chemical_count:,} 个。{hint}"
        )

    RAW.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    archived = ARCHIVE / source.name
    if source != archived.resolve():
        shutil.copy2(source, archived)
    frame.to_csv(RAW / "isscan_raw.csv", index=False)
    print(
        f"isscan_raw.csv：{len(frame):,} 行 x {len(frame.columns)} 列；"
        f"{chemical_count:,} 个化学物；"
        f"来源文件已归档至 {archived.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
