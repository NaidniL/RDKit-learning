"""下载与 CPDB、CCRIS 和 IRIS 来源记录关联的化学结构。

CPDB 和 CCRIS 结构来自相应 NLM 原始数据源提交的 PubChem Substance 记录。
IRIS 记录使用官方导出文件中的 EPA DTXSID 进行精确解析。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
from rdkit import Chem


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
USER_AGENT = "carcinogenicity-benchmark/0.1 (research data retrieval)"
SDF_BATCH_SIZE = 100
REQUEST_INTERVAL_SECONDS = 0.22

SOURCE_CONFIG = {
    "cpdb": {
        "pubchem_name": "Carcinogenic Potency Database (CPDB)",
        "expected_records": 1547,
    },
    "ccris": {
        "pubchem_name": (
            "Chemical Carcinogenesis Research Information System (CCRIS)"
        ),
        "expected_records": 9562,
    },
}


def request_bytes(url: str, attempts: int = 6) -> bytes:
    """在公共 API 限流时使用有界重试和退避策略请求 URL。"""
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=120) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                raise
            if error.code not in {429, 500, 502, 503, 504}:
                raise
        except URLError:
            pass
        if attempt == attempts - 1:
            raise RuntimeError(f"尝试 {attempts} 次后仍下载失败：{url}")
        time.sleep(min(2**attempt, 30))
    raise AssertionError("执行到理论上不可达的代码")


def chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def sdf_properties(record: str) -> dict[str, str]:
    pattern = re.compile(r"^> <([^>]+)>\r?\n(.*?)(?=\r?\n\r?\n|\Z)", re.M | re.S)
    return {name: value.strip() for name, value in pattern.findall(record)}


def source_smiles(record: str) -> tuple[str, str]:
    end = record.find("M  END")
    if end < 0:
        return "", "缺少MolBlock"
    molblock = record[: end + len("M  END")]
    molecule = Chem.MolFromMolBlock(
        molblock, sanitize=False, removeHs=False, strictParsing=False
    )
    if molecule is None:
        return "", "MolBlock无效"
    try:
        Chem.SanitizeMol(molecule)
        molecule = Chem.RemoveHs(molecule)
        return Chem.MolToSmiles(molecule, canonical=False, isomericSmiles=True), ""
    except (ValueError, RuntimeError) as error:
        return "", f"RDKit错误：{type(error).__name__}"


def parse_source_sdf(path: Path, source: str) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8", errors="replace")
    records = [record.strip() for record in text.split("$$$$") if record.strip()]
    rows = []
    for record in records:
        properties = sdf_properties(record)
        smiles, error = source_smiles(record)
        comment = properties.get("PUBCHEM_SUBSTANCE_COMMENT", "")
        ccris_match = re.search(r"CCRIS Record Number:\s*(\d+)", comment)
        synonyms = properties.get("PUBCHEM_SUBSTANCE_SYNONYM", "").splitlines()
        casrn = properties.get("PUBCHEM_GENERIC_REGISTRY_NAME", "")
        rows.append(
            {
                "source": source,
                "source_record_id": (
                    ccris_match.group(1)
                    if ccris_match
                    else properties.get("PUBCHEM_EXT_DATASOURCE_REGID", "")
                ),
                "source_registry_id": properties.get(
                    "PUBCHEM_EXT_DATASOURCE_REGID", ""
                ),
                "casrn": casrn,
                "name": next((value for value in synonyms if value != casrn), ""),
                "pubchem_sid": properties.get("PUBCHEM_SUBSTANCE_ID", ""),
                "pubchem_cid": properties.get("PUBCHEM_CID_ASSOCIATIONS", "")
                .splitlines()[0]
                .split()[0]
                if properties.get("PUBCHEM_CID_ASSOCIATIONS")
                else "",
                "source_smiles": smiles,
                "structure_status": "resolved" if smiles else "unresolved",
                "structure_error": error,
                "structure_provenance": "PubChem Substance；原始数据提交方",
            }
        )
    return pd.DataFrame(rows)


def download_depositor_source(source: str, force: bool) -> None:
    config = SOURCE_CONFIG[source]
    archive = RAW / "source_archives" / source
    archive.mkdir(parents=True, exist_ok=True)
    sid_path = archive / "pubchem_source_sids.json"
    sdf_path = archive / "pubchem_source_substances.sdf"

    encoded_name = quote(str(config["pubchem_name"]), safe="")
    if force or not sid_path.exists():
        sid_url = f"{PUBCHEM}/substance/sourceall/{encoded_name}/sids/JSON"
        sid_path.write_bytes(request_bytes(sid_url))
    sid_data = json.loads(sid_path.read_text(encoding="utf-8"))
    sids = [int(value) for value in sid_data["IdentifierList"]["SID"]]
    expected = int(config["expected_records"])
    if len(sids) != expected:
        raise ValueError(
            f"{source}：预期 {expected} 个来源 SID，实际为 {len(sids)} 个"
        )

    if force or not sdf_path.exists():
        parts = archive / ".pubchem_sdf_parts"
        if force and parts.exists():
            shutil.rmtree(parts)
        parts.mkdir(exist_ok=True)
        batches = list(chunks(sids, SDF_BATCH_SIZE))
        for index, batch in enumerate(batches, start=1):
            part = parts / f"{index:04d}.sdf"
            if not part.exists():
                sid_list = ",".join(map(str, batch))
                part.write_bytes(
                    request_bytes(f"{PUBCHEM}/substance/sid/{sid_list}/SDF")
                )
                time.sleep(REQUEST_INTERVAL_SECONDS)
            print(f"{source}：SDF 批次 {index}/{len(batches)}", flush=True)
        with sdf_path.open("wb") as output:
            for part in sorted(parts.glob("*.sdf")):
                output.write(part.read_bytes())
        shutil.rmtree(parts)

    frame = parse_source_sdf(sdf_path, source)
    if len(frame) != expected:
        raise ValueError(
            f"{source}：预期 {expected} 条 SDF 记录，实际解析 {len(frame)} 条"
        )
    frame.to_csv(RAW / f"{source}_structures_raw.csv", index=False)
    print(
        f"{source}_structures_raw.csv：{len(frame):,} 条记录；"
        f"{(frame['structure_status'] == 'resolved').sum():,} 个结构"
    )


def download_iris_structures(force: bool) -> None:
    iris = pd.read_csv(RAW / "iris_raw.csv", dtype=str, keep_default_na=False)
    archive = RAW / "source_archives" / "iris"
    cache_path = archive / "pubchem_dtxsid_properties.jsonl"
    cached: dict[str, dict[str, object]] = {}
    if cache_path.exists() and not force:
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            cached[str(record["query_dtxsid"])] = record

    def fetch_dtxsid(dtxsid: str) -> dict[str, object]:
        property_names = "Title,ConnectivitySMILES,SMILES,InChIKey"
        url = f"{PUBCHEM}/compound/name/{quote(dtxsid, safe='')}/property/{property_names}/JSON"
        try:
            response = json.loads(request_bytes(url))
            properties = response["PropertyTable"]["Properties"]
            return {
                "query_dtxsid": dtxsid,
                "status": "resolved" if len(properties) == 1 else "ambiguous",
                "properties": properties,
            }
        except HTTPError as error:
            if error.code != 404:
                raise
            return {
                "query_dtxsid": dtxsid,
                "status": "not_found",
                "properties": [],
            }

    def save_cache() -> None:
        with cache_path.open("w", encoding="utf-8") as output:
            for dtxsid in iris["DTXSID"]:
                if dtxsid and dtxsid in cached:
                    output.write(json.dumps(cached[dtxsid], ensure_ascii=False) + "\n")

    pending = [
        dtxsid for dtxsid in iris["DTXSID"] if dtxsid and dtxsid not in cached
    ]
    completed = len(cached)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_dtxsid, dtxsid): dtxsid for dtxsid in pending}
        for future in as_completed(futures):
            dtxsid = futures[future]
            cached[dtxsid] = future.result()
            completed += 1
            print(f"iris：DTXSID {completed}/{len(iris)}", flush=True)
            if completed % 25 == 0:
                save_cache()

    save_cache()

    rows = []
    for raw in iris.to_dict(orient="records"):
        dtxsid = raw["DTXSID"]
        result = cached.get(
            dtxsid, {"query_dtxsid": dtxsid, "status": "missing_dtxsid", "properties": []}
        )
        properties = result["properties"]
        prop = properties[0] if len(properties) == 1 else {}
        error_messages = {
            "ambiguous": "匹配结果不唯一",
            "not_found": "未找到匹配结构",
            "missing_dtxsid": "缺少DTXSID",
        }
        rows.append(
            {
                "source": "iris",
                "source_record_id": dtxsid or raw["CASRN"],
                "dtxsid": dtxsid,
                "casrn": raw["CASRN"],
                "name": raw["CHEMICAL NAME"],
                "pubchem_cid": prop.get("CID", ""),
                "source_smiles": prop.get("SMILES", ""),
                "connectivity_smiles": prop.get("ConnectivitySMILES", ""),
                "pubchem_inchikey": prop.get("InChIKey", ""),
                "structure_status": result["status"],
                "structure_error": error_messages.get(str(result["status"]), ""),
                "structure_provenance": "PubChem DTXSID 精确查询（EPA 标识符）",
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(RAW / "iris_structures_raw.csv", index=False)
    print(
        f"iris_structures_raw.csv：{len(frame):,} 条记录；"
        f"{(frame['structure_status'] == 'resolved').sum():,} 个结构"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="下载与原始数据源关联的化学结构")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["cpdb", "ccris", "iris"],
        default=["cpdb", "ccris", "iris"],
    )
    parser.add_argument("--force", action="store_true", help="强制重新下载已缓存的记录")
    args = parser.parse_args()

    for source in args.sources:
        if source == "iris":
            download_iris_structures(args.force)
        else:
            download_depositor_source(source, args.force)


if __name__ == "__main__":
    main()
