# agent.py
"""
XLSX/PDF → intermediate(.intermediate.jsonl/.csv) → PII(.pii.jsonl/.csv)

- 모듈로 import해서 UI/다른 코드에서 run_agent_on_paths(...) 호출 가능
- CLI로도 실행 가능: python agent.py <files/dirs> [옵션]

의존 모듈
- xlsx_to_intermediate.py : xlsx_to_records, dump_jsonl, dump_csv
- pdf_to_intermediate.py  : pdf_text_records, pdf_table_records, dump_jsonl, dump_csv
- filter_pii_from_intermediate.py :
    - filter_records(records, dedupe_mode=..., debug_drops=...)
    - aggregate_pdf_lines(records, y_tol=...)
    - dump_jsonl, dump_csv
"""

import argparse
import sys
import traceback
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# --- 기존 모듈 import ---
from xlsx_to_intermediate import (
    xlsx_to_records,
    dump_jsonl as dump_jsonl_xlsx,
    dump_csv as dump_csv_xlsx,
)
from pdf_to_intermediate import (
    pdf_text_records,
    pdf_table_records,
    dump_jsonl as dump_jsonl_pdf,
    dump_csv as dump_csv_pdf,
)
from filter_pii_from_intermediate import (
    filter_records as pii_filter_records,
    aggregate_pdf_lines,
    dump_jsonl as dump_jsonl_pii,
    dump_csv as dump_csv_pii,
)

# -----------------------
# 내부 유틸
# -----------------------
def _discover_inputs(target: Path, recurse: bool):
    """파일 또는 디렉터리 입력을 확정(.xlsx/.pdf만)."""
    if target.is_file():
        yield target
    else:
        pattern = "**/*" if recurse else "*"
        for p in target.glob(pattern):
            if p.is_file() and p.suffix.lower() in {".xlsx", ".pdf"}:
                yield p

def _make_intermediate(
    input_path: Path,
    out_prefix: str,
    *,
    pdf_mode: str = "both",
    aggregate_lines: bool = False,
    line_y_tol: float = 2.5,
) -> Path:
    """
    입력(.xlsx/.pdf) → 중간 산출물 저장 후 JSONL 경로 반환
    - out_prefix.intermediate.jsonl
    - out_prefix.intermediate.csv
    """
    ext = input_path.suffix.lower()
    inter_jsonl = Path(f"{out_prefix}.intermediate.jsonl")
    inter_csv   = Path(f"{out_prefix}.intermediate.csv")

    if ext == ".xlsx":
        recs = list(xlsx_to_records(str(input_path)))
        dump_jsonl_xlsx(recs, str(inter_jsonl))
        dump_csv_xlsx(recs, str(inter_csv))

    elif ext == ".pdf":
        recs: List[Dict] = []
        if pdf_mode in ("text", "both"):
            recs.extend(pdf_text_records(str(input_path)))
        if pdf_mode in ("table", "both"):
            recs.extend(pdf_table_records(str(input_path)))
        if aggregate_lines:
            # pdf_text 토큰으로 합성된 라인도 함께 저장(추가 신호)
            recs = recs + aggregate_pdf_lines(recs, y_tol=line_y_tol)

        dump_jsonl_pdf(recs, str(inter_jsonl))
        dump_csv_pdf(recs, str(inter_csv))

    else:
        raise ValueError(f"지원하지 않는 확장자: {ext}")

    return inter_jsonl

def _iter_jsonl(path: str) -> Iterable[Dict]:
    import json
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                yield json.loads(s)

def _run_filter(
    intermediate_jsonl: Path,
    out_prefix: str,
    *,
    dedupe: str = "by_location",
    debug_drops: bool = False,
):
    """
    intermediate JSONL을 읽어 PII 필터 → .pii.jsonl/.pii.csv 저장
    """
    rows = list(pii_filter_records(_iter_jsonl(str(intermediate_jsonl)),
                                   dedupe_mode=dedupe,
                                   debug_drops=debug_drops))
    out_jsonl = Path(f"{out_prefix}.pii.jsonl")
    out_csv   = Path(f"{out_prefix}.pii.csv")
    dump_jsonl_pii(rows, str(out_jsonl))
    dump_csv_pii(rows, str(out_csv))
    return out_jsonl, out_csv, len(rows)

# -----------------------
# 공개 API (UI/스크립트 공용)
# -----------------------
def run_agent_on_paths(
    inputs: List[Path],
    *,
    out_dir: Optional[Path] = None,
    recurse: bool = False,
    pdf_mode: str = "both",          # text/table/both
    aggregate_lines: bool = True,    # pdf_text → 라인 집계 추가
    line_y_tol: float = 2.5,
    dedupe: str = "by_location",     # by_location/by_id/by_text/none
    debug_drops: bool = False,
    stop_on_error: bool = False,
) -> List[Dict]:
    """
    파일/디렉터리 목록을 받아 intermediate → PII까지 일괄 처리.
    반환: [{ in_path, out_prefix, inter_jsonl, pii_jsonl, pii_csv, pii_rows } ...]
    """
    # 입력 확정
    final_inputs: List[Path] = []
    for p in inputs:
        p = p.resolve()
        if not p.exists():
            continue
        for found in _discover_inputs(p, recurse):
            final_inputs.append(found)

    results: List[Dict] = []
    if not final_inputs:
        return results

    for in_path in final_inputs:
        try:
            base = in_path.stem
            odir = out_dir.resolve() if out_dir else in_path.parent
            odir.mkdir(parents=True, exist_ok=True)
            out_prefix = str(odir / base)

            # 1) intermediate 생성
            inter_jsonl = _make_intermediate(
                in_path,
                out_prefix,
                pdf_mode=pdf_mode,
                aggregate_lines=aggregate_lines,
                line_y_tol=line_y_tol,
            )

            # 2) PII 필터
            pii_jsonl, pii_csv, n = _run_filter(
                inter_jsonl,
                out_prefix,
                dedupe=dedupe,
                debug_drops=debug_drops,
            )

            results.append({
                "in_path": str(in_path),
                "out_prefix": out_prefix,
                "inter_jsonl": str(inter_jsonl),
                "pii_jsonl": str(pii_jsonl),
                "pii_csv": str(pii_csv),
                "pii_rows": int(n),
            })

        except Exception as e:
            if stop_on_error:
                raise
            results.append({
                "in_path": str(in_path),
                "error": str(e),
                "trace": traceback.format_exc(),
            })
            continue

    return results

# -----------------------
# CLI
# -----------------------
def main():
    ap = argparse.ArgumentParser(description="Agent: XLSX/PDF → intermediate → PII(8종) 필터")
    ap.add_argument("inputs", nargs="+", help="파일(.xlsx/.pdf) 또는 디렉터리(복수 가능)")
    ap.add_argument("--recurse", action="store_true", help="디렉터리 입력 시 하위 폴더까지 탐색")
    ap.add_argument("--out-dir", default="", help="출력 디렉터리(기본: 입력 파일 위치)")
    ap.add_argument("--pdf-mode", choices=["text","table","both"], default="both", help="PDF 처리 모드")
    ap.add_argument("--aggregate-lines", action="store_true", help="PDF 텍스트 라인 집계 활성화")
    ap.add_argument("--line-y-tol", type=float, default=2.5, help="라인 집계 y tolerance")
    ap.add_argument("--dedupe", choices=["by_location","by_id","by_text","none"], default="by_location",
                    help="PII 중복 제거 기준")
    ap.add_argument("--debug-drops", action="store_true", help="드랍 후보를 디버그 캐시에 남김")
    ap.add_argument("--stop-on-error", action="store_true", help="에러 시 즉시 중단")
    args = ap.parse_args()

    inputs = [Path(x) for x in args.inputs]
    out_dir = Path(args.out_dir) if args.out_dir else None

    results = run_agent_on_paths(
        inputs,
        out_dir=out_dir,
        recurse=args.recurse,
        pdf_mode=args.pdf_mode,
        aggregate_lines=args.aggregate_lines,
        line_y_tol=args.line_y_tol,
        dedupe=args.dedupe,
        debug_drops=args.debug_drops,
        stop_on_error=args.stop_on_error,
    )

    if not results:
        print("[ERR] 처리할 입력이 없습니다.", file=sys.stderr)
        sys.exit(1)

    for r in results:
        if "error" in r:
            print(f"[ERR] {r['in_path']}: {r['error']}", file=sys.stderr)
            print(r["trace"], file=sys.stderr)
        else:
            print(f"\n[AGENT] Processing: {r['in_path']}")
            print(f"[OK] Intermediate: {r['inter_jsonl']}")
            print(f"[OK] PII: {r['pii_jsonl']} / {r['pii_csv']} (rows={r['pii_rows']})")

if __name__ == "__main__":
    main()
