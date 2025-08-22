# xlsx_to_intermediate.py
import argparse, csv, json, hashlib
from pathlib import Path
from typing import Dict, Iterable
import pandas as pd

KEYS = ["id","source_path","source_type","container","row","col","header","bbox","text"]

def _mk_id(*parts) -> str:
    return hashlib.sha256("||".join(map(str, parts)).encode()).hexdigest()[:16]

def xlsx_to_records(xlsx_path: str) -> Iterable[Dict]:
    xlsx_path = str(Path(xlsx_path).resolve())
    xls = pd.ExcelFile(xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet, dtype=str)
        headers = list(df.columns)
        for r_idx in range(df.shape[0]):
            for c_idx, colname in enumerate(headers):
                val = df.iat[r_idx, c_idx]
                if pd.isna(val):
                    continue
                yield {
                    "id": _mk_id(xlsx_path,"xlsx",sheet,r_idx+1,c_idx+1,str(val)[:50]),
                    "source_path": xlsx_path,
                    "source_type": "xlsx",
                    "container": sheet,         # 시트명
                    "row": r_idx + 1,          # 1-based
                    "col": c_idx + 1,
                    "header": str(colname),
                    "bbox": None,              # XLSX 좌표 개념 없음
                    "text": str(val),
                }

def dump_jsonl(records: Iterable[Dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def dump_csv(records: Iterable[Dict], out_path: str):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEYS)
        w.writeheader()
        for r in records:
            row = dict(r)
            row["bbox"] = json.dumps(row["bbox"], ensure_ascii=False) if row.get("bbox") is not None else ""
            w.writerow({k: row.get(k, "") for k in KEYS})

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="XLSX → intermediate(JSONL/CSV)")
    ap.add_argument("xlsx", type=str)
    ap.add_argument("--out-prefix", default="")
    args = ap.parse_args()

    p = Path(args.xlsx)
    if not p.exists():
        raise SystemExit(f"입력 경로 없음: {p}")

    prefix = args.out_prefix or p.with_suffix("").as_posix()
    recs = list(xlsx_to_records(str(p)))
    dump_jsonl(recs, f"{prefix}.xlsx.intermediate.jsonl")
    dump_csv(recs, f"{prefix}.xlsx.intermediate.csv")
    print(f"[OK] XLSX → {len(recs)} rows")
