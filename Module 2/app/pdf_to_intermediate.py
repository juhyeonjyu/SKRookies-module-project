# pdf_to_intermediate.py
import argparse, csv, json, hashlib
from pathlib import Path
from typing import Dict, Iterable, List
import pdfplumber
import pandas as pd

KEYS = ["id","source_path","source_type","container","row","col","header","bbox","text"]

def _mk_id(*parts) -> str:
    return hashlib.sha256("||".join(map(str, parts)).encode()).hexdigest()[:16]

def pdf_text_records(pdf_path: str) -> Iterable[Dict]:
    pdf_path = str(Path(pdf_path).resolve())
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1.0, y_tolerance=1.0, keep_blank_chars=False)
            for w in words:
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                x0, x1, top, bottom = float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"])
                yield {
                    "id": _mk_id(pdf_path,"pdf_text",pno,x0,top,text),
                    "source_path": pdf_path,
                    "source_type": "pdf_text",
                    "container": f"page={pno}",
                    "row": None, "col": None,
                    "header": "",
                    "bbox": [x0, top, x1, bottom],  # PDF 좌표
                    "text": text,
                }

def pdf_table_records(pdf_path: str) -> Iterable[Dict]:
    pdf_path = str(Path(pdf_path).resolve())
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for ti, table in enumerate(tables, start=1):
                df = pd.DataFrame(table).fillna("")
                if df.empty:
                    continue
                headers = list(df.iloc[0])
                data = df.iloc[1:].reset_index(drop=True)
                for r_idx in range(data.shape[0]):
                    for c_idx in range(data.shape[1]):
                        val = str(data.iat[r_idx, c_idx]).strip()
                        if not val:
                            continue
                        header = str(headers[c_idx]) if c_idx < len(headers) else ""
                        yield {
                            "id": _mk_id(pdf_path,"pdf_table",pno,ti,r_idx+1,c_idx+1,val[:50]),
                            "source_path": pdf_path,
                            "source_type": "pdf_table",
                            "container": f"page={pno},table_{ti}",
                            "row": r_idx + 1,
                            "col": c_idx + 1,
                            "header": header,
                            "bbox": None,  # pdfplumber 기본 테이블 API는 좌표 미포함
                            "text": val,
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
    ap = argparse.ArgumentParser(description="PDF → intermediate(JSONL/CSV) using pdfplumber")
    ap.add_argument("pdf", type=str)
    ap.add_argument("--out-prefix", default="")
    ap.add_argument("--mode", choices=["text","table","both"], default="both")
    args = ap.parse_args()

    p = Path(args.pdf)
    if not p.exists():
        raise SystemExit(f"입력 경로 없음: {p}")

    prefix = args.out_prefix or p.with_suffix("").as_posix()

    recs: List[Dict] = []
    if args.mode in ("text","both"):
        recs.extend(list(pdf_text_records(str(p))))
    if args.mode in ("table","both"):
        recs.extend(list(pdf_table_records(str(p))))

    dump_jsonl(recs, f"{prefix}.pdf.intermediate.jsonl")
    dump_csv(recs, f"{prefix}.pdf.intermediate.csv")
    print(f"[OK] PDF({args.mode}) → {len(recs)} rows")
