"""将权威来源归档转换为稳定的 UTF-8 raw CSV 文件。"""

from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ARCHIVES = RAW / "source_archives"


def clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.dropna(how="all").reset_index(drop=True)


def build_cpdb() -> None:
    cpdb = ARCHIVES / "cpdb"
    # "nan" 是 5-NITRO-o-ANISIDINE 的合法 CPDB chemcode，不是缺失值。
    names = clean_frame(
        pd.read_excel(cpdb / "cpdb.chemname.xls", keep_default_na=False)
    )

    studies = []
    for filename, source_table in (
        ("cpdb.lit.xls", "general_literature"),
        ("cpdb.ncintp.xls", "nci_ntp"),
    ):
        frame = clean_frame(pd.read_excel(cpdb / filename, keep_default_na=False))
        frame.insert(0, "source_table", source_table)
        studies.append(frame)

    merged = pd.concat(studies, ignore_index=True, sort=False).merge(
        names[["chemcode", "name", "cas"]],
        on="chemcode",
        how="left",
        validate="many_to_one",
    )
    merged.to_csv(RAW / "cpdb_raw.csv", index=False)


def records_json(frame: pd.DataFrame) -> str:
    records = frame.where(pd.notna(frame), None).to_dict(orient="records")
    return json.dumps(records, ensure_ascii=False, default=str)


def build_iris() -> None:
    path = ARCHIVES / "iris" / "iris_downloads_database_export_april2025.xlsx"
    chemical = clean_frame(pd.read_excel(path, sheet_name="Chemical Details"))
    details = clean_frame(pd.read_excel(path, sheet_name="WOE Details"))
    toxicity = clean_frame(pd.read_excel(path, sheet_name="WOE Toxicity Values"))

    keys = ["CHEMICAL NAME", "CASRN"]
    details_grouped = {
        key: records_json(group.drop(columns=keys))
        for key, group in details.groupby(keys, dropna=False, sort=False)
    }
    toxicity_grouped = {
        key: records_json(group.drop(columns=keys))
        for key, group in toxicity.groupby(keys, dropna=False, sort=False)
    }

    rows = []
    for record in chemical.where(pd.notna(chemical), None).to_dict(orient="records"):
        key = (record["CHEMICAL NAME"], record["CASRN"])
        record["WOE DETAILS JSON"] = details_grouped.get(key, "[]")
        record["WOE TOXICITY VALUES JSON"] = toxicity_grouped.get(key, "[]")
        rows.append(record)
    pd.DataFrame(rows).to_csv(RAW / "iris_raw.csv", index=False)


def element_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def children_as_records(document: ET.Element, tag: str) -> list[dict[str, object]]:
    records = []
    for child in document.findall(tag):
        values: defaultdict[str, list[str]] = defaultdict(list)
        for field in child:
            value = element_text(field)
            if value:
                values[field.tag].append(value)
        records.append(
            {
                key: values_list[0] if len(values_list) == 1 else values_list
                for key, values_list in values.items()
            }
        )
    return records


def build_ccris() -> None:
    path = ARCHIVES / "ccris" / "ccris.xml.20110828.zip"
    rows = []
    with zipfile.ZipFile(path) as archive:
        xml_name = archive.namelist()[0]
        with archive.open(xml_name) as source:
            for _, document in ET.iterparse(source, events=("end",)):
                if document.tag != "DOC":
                    continue
                scalar: defaultdict[str, list[str]] = defaultdict(list)
                for child in document:
                    if child.tag not in {"cstu", "istu", "mstu", "tstu"}:
                        value = element_text(child)
                        if value:
                            scalar[child.tag].append(value)
                row: dict[str, object] = {
                    key: values[0] if len(values) == 1 else json.dumps(values)
                    for key, values in scalar.items()
                }
                for tag, column in (
                    ("cstu", "carcinogenicity_studies_json"),
                    ("istu", "initiation_studies_json"),
                    ("mstu", "mutagenicity_studies_json"),
                    ("tstu", "tumor_promotion_studies_json"),
                ):
                    row[column] = json.dumps(
                        children_as_records(document, tag), ensure_ascii=False
                    )
                rows.append(row)
                document.clear()
    pd.DataFrame(rows).to_csv(RAW / "ccris_raw.csv", index=False)


def main() -> None:
    build_cpdb()
    build_iris()
    build_ccris()
    for filename in ("cpdb_raw.csv", "iris_raw.csv", "ccris_raw.csv"):
        frame = pd.read_csv(RAW / filename, low_memory=False)
        print(f"{filename}：{len(frame):,} 行 x {len(frame.columns)} 列")


if __name__ == "__main__":
    main()
