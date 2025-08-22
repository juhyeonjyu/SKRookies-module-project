# filter_pii_from_intermediate.py
# 역할:
#  - intermediate(JSONL/CSV)에서 8종 PII만 선별
#  - 옵션: pdf_text → 라인 집계(--aggregate-lines) 후 추가 검출
#  - dedupe 기본: '위치(row/col) 우선' (동일 텍스트여도 다른 위치면 보존)
#  - --debug-drops 로 드랍 사유를 .pii_dropped.jsonl에 기록
#
# 사용 예:
#   python filter_pii_from_intermediate.py test.intermediate.csv --aggregate-lines --line-y-tol 2.5
#   python filter_pii_from_intermediate.py test.intermediate.csv --dedupe none --debug-drops
#   python filter_pii_from_intermediate.py test.intermediate.jsonl --dedupe by_location

import argparse, csv, json, re
from pathlib import Path
from typing import Dict, Iterable, List
from collections import defaultdict

from detectors_pii import classify_text  # 사용자 제공 분류기

# 선별 유지 대상(8종)
KEEP = {"name","passport","driver_license","rrn","address","email","phone","card"}

# 출력 키(고정 헤더)
KEYS_OUT = ["id","pii_type","source_path","source_type","container","row","col","header","bbox","text"]

# 인라인 성명 패턴: "성명: 홍길동" / "이름 홍길동"
NAME_INLINE_RE = re.compile(r'(성명|이름)\s*[: ]?\s*([가-힣]{2,4})')

# 헤더 기반 보강용(대/소문자/공백 무시)
NAME_HEADERS    = {"성명","이름","한글이름","영문이름","대표자","담당자","name","full name"}
EMAIL_HEADERS   = {"이메일","email","email 주소"}
PHONE_HEADERS   = {"연락처","전화","전화번호","mobile","phone"}
ADDRESS_HEADERS = {"주소","집주소","address"}

# 제로폭 문자/하이픈 표준화
_ZW_CHARS = dict.fromkeys(map(ord, ["\u200b","\u200c","\u200d","\ufeff","\u2060"]), None)
def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = s.translate(_ZW_CHARS)
    s = (s.replace("\u2010","-").replace("\u2011","-")
           .replace("\u2012","-").replace("\u2013","-").replace("\u2014","-"))
    return " ".join(s.split())

# ---------------- pdf_text → pdf_line 집계 ----------------
def aggregate_pdf_lines(records: List[Dict], y_tol: float = 2.0) -> List[Dict]:
    """
    같은 페이지(container) 내에서 y(top) 좌표가 가까운 토큰을 묶어 한 줄로 결합.
    bbox는 합치지 않고 None으로 둠.
    """
    by_container = defaultdict(list)
    for r in records:
        if r.get("source_type") == "pdf_text" and isinstance(r.get("bbox"), list):
            by_container[r.get("container","")].append(r)

    synthetic = []
    for container, toks in by_container.items():
        # y, x 순 정렬
        toks.sort(key=lambda x: (float(x["bbox"][1]), float(x["bbox"][0])))
        buckets = []
        for t in toks:
            y = float(t["bbox"][1])
            placed = False
            for b in buckets:
                if abs(y - b["y_ref"]) <= y_tol:
                    b["toks"].append(t); placed = True; break
            if not placed:
                buckets.append({"y_ref": y, "toks": [t]})

        for b in buckets:
            b["toks"].sort(key=lambda x: float(x["bbox"][0]))
            line_text = " ".join(normalize_text(x.get("text","")) for x in b["toks"]).strip()
            if not line_text:
                continue
            synthetic.append({
                "id": f'line::{container}::{int(round(b["y_ref"]))}',
                "source_path": b["toks"][0].get("source_path",""),
                "source_type": "pdf_line",
                "container": container,
                "row": None, "col": None,
                "header": "",
                "bbox": None,
                "text": line_text,
            })
    return synthetic

# ---------------- I/O 유틸 ----------------
def iter_jsonl(path: str) -> Iterable[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                yield json.loads(s)

def dump_jsonl(records: Iterable[Dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def dump_csv(records: Iterable[Dict], out_path: str):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEYS_OUT)
        w.writeheader()
        for r in records:
            row = dict(r)
            if isinstance(row.get("bbox"), (list, dict)):
                row["bbox"] = json.dumps(row["bbox"], ensure_ascii=False)
            w.writerow({k: row.get(k, "") for k in KEYS_OUT})

# ---------------- dedupe 키 ----------------
def _dedupe_key(rec: Dict, mode: str = "by_location") -> tuple:
    """
    모드:
      - by_location(기본): (source_path, container, row, col, pii_type) → 위치 우선
      - by_id          : id가 있으면 id 기반
      - by_text        : (pii_type, source_path, container, header, text, bbox) → 폴백 강화
      - none           : dedupe 비활성화
    """
    if mode == "none":
        return ("none", id(rec))
    if mode == "by_id" and rec.get("id"):
        return ("id", rec["id"])
    if mode == "by_location":
        sp = rec.get("source_path",""); cont = rec.get("container","")
        row = rec.get("row"); col = rec.get("col")
        if row not in (None,"","None") and col not in (None,"","None"):
            return ("loc", sp, cont, str(row), str(col), (rec.get("pii_type") or ""))
        # 위치 정보가 없으면 텍스트 기반으로 폴백

    # ✅ 폴백 강화: header/bbox 포함 → 동명이인 보존
    sp = rec.get("source_path",""); cont = rec.get("container","")
    header = rec.get("header","")
    bbox = rec.get("bbox","")
    bbox_sig = json.dumps(bbox, ensure_ascii=False) if isinstance(bbox, (list, dict)) else str(bbox)
    return ("text",
            (rec.get("pii_type") or ""),
            sp, cont,
            header,
            rec.get("text",""),
            bbox_sig)

# ---------------- 핵심 필터 ----------------
def filter_records(records: Iterable[Dict], *, dedupe_mode: str="by_location", debug_drops: bool=False) -> Iterable[Dict]:
    """
    1) 텍스트 정규화 후 classify_text
    2) KEEP(8종)만 선별 (헤더 기반 보강 포함)
    3) dedupe_mode 기준으로 중복 제거
    4) pdf_line에서 인라인 성명 추가 탐지
    5) debug_drops=True면 드랍 사유 기록
    """
    seen = set()
    dropped = []  # 디버그용
    name_headers_norm = {h.strip().lower() for h in NAME_HEADERS}
    email_headers_norm = {h.strip().lower() for h in EMAIL_HEADERS}
    phone_headers_norm = {h.strip().lower() for h in PHONE_HEADERS}
    address_headers_norm = {h.strip().lower() for h in ADDRESS_HEADERS}

    # 1차: 개별 레코드 분류
    for r in records:
        ctx = {
            "header": r.get("header",""),
            "container": r.get("container",""),
            "source_type": r.get("source_type",""),
        }
        text_norm = normalize_text(r.get("text",""))
        header_norm = (r.get("header","") or "").strip().lower()

        # 분류 + 표준화
        t = classify_text(text_norm, ctx)
        t = (t or "").strip().lower()

        # ✅ 헤더 기반 보강(분류가 실패했을 때만)
        if t not in KEEP:
            # name 보강
            if header_norm in name_headers_norm:
                core = text_norm.replace(" ", "").replace("·", "")
                # 길이 sanity check (한글/영문 혼합 고려해 완화)
                if 1 <= len(core) <= 50:
                    t = "name"
            # email/phone/address도 최소한의 보강 (선택)
            elif header_norm in email_headers_norm:
                t = "email"
            elif header_norm in phone_headers_norm:
                t = "phone"
            elif header_norm in address_headers_norm:
                t = "address"

        if t in KEEP:
            out = dict(r)
            out["text"] = text_norm
            out["pii_type"] = t
            sig = _dedupe_key(out, dedupe_mode)
            if sig in seen:
                if debug_drops:
                    d = dict(out); d["_drop_reason"] = f"dedupe:{dedupe_mode}"
                    dropped.append(d)
                continue
            seen.add(sig)
            yield out
        else:
            if debug_drops:
                d = dict(r); d["_drop_reason"] = "classify:None"; d["_norm_text"] = text_norm
                dropped.append(d)

    # 2차: 라인 기반 인라인 "성명/이름" 패턴 추가
    for r in records:
        if r.get("source_type") == "pdf_line":
            line = normalize_text(r.get("text",""))
            m = NAME_INLINE_RE.search(line)
            if m:
                name = m.group(2)
                if 2 <= len(name) <= 4:
                    out = dict(r)
                    out["text"] = name
                    out["pii_type"] = "name"
                    sig = _dedupe_key(out, dedupe_mode)
                    if sig in seen:
                        if debug_drops:
                            d = dict(out); d["_drop_reason"] = f"dedupe:{dedupe_mode}"
                            dropped.append(d)
                        continue
                    seen.add(sig)
                    yield out

    # 디버그 캐시 저장 (메인에서 파일로 덤프)
    if debug_drops and dropped:
        globals().setdefault("_PII_DROPPED_CACHE", []).extend(dropped)

# ---------------- 메인 ----------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Intermediate(JSONL/CSV) → 8종 PII 필터")
    ap.add_argument("intermediate", help=".intermediate.jsonl 또는 .intermediate.csv")
    ap.add_argument("--out-prefix", default="")
    ap.add_argument("--aggregate-lines", action="store_true", help="pdf_text 토큰을 라인 단위로 집계 후 추가 판정")
    ap.add_argument("--line-y-tol", type=float, default=2.0, help="라인 집계 y tolerance")
    ap.add_argument("--dedupe", choices=["by_location","by_id","by_text","none"], default="by_location",
                    help="중복 제거 기준 (기본: 위치 기준, none=중복 제거 안 함)")
    ap.add_argument("--debug-drops", action="store_true", help="드랍된 후보를 *.pii_dropped.jsonl 로 기록")
    args = ap.parse_args()

    p = Path(args.intermediate)
    if not p.exists():
        raise SystemExit(f"입력 경로 없음: {p}")

    prefix = args.out_prefix or p.with_suffix("").as_posix().replace(".intermediate","")
    suffix = p.suffix.lower()

    # 1) 입력 로딩
    if suffix == ".jsonl":
        records = list(iter_jsonl(str(p)))
    elif suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(str(p), dtype=str, keep_default_na=False)
        def parse_bbox(s: str):
            s = (s or "").strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    return json.loads(s)
                except Exception:
                    return ""
            return ""
        records = []
        for _, x in df.iterrows():
            rec = {k: x.get(k, "") for k in df.columns}
            if "bbox" in rec:
                rec["bbox"] = parse_bbox(rec["bbox"])
            records.append(rec)
    else:
        raise SystemExit("지원 입력: .jsonl 또는 .csv")

    # 2) 라인 집계(옵션)
    if args.aggregate_lines:
        extra = aggregate_pdf_lines(records, y_tol=args.line_y_tol)
        records = records + extra

    # 3) 필터링 + dedupe + 드랍 로깅
    rows = list(filter_records(records, dedupe_mode=args.dedupe, debug_drops=args.debug_drops))

    # 4) 저장
    out_jsonl = f"{prefix}.pii.jsonl"
    out_csv   = f"{prefix}.pii.csv"
    dump_jsonl(rows, out_jsonl)
    dump_csv(rows, out_csv)

    print(f"[OK] PII rows: {len(rows)}")
    print(f" - {out_jsonl}")
    print(f" - {out_csv}")

    # 5) 드랍 로그 저장
    if args.debug_drops and globals().get("_PII_DROPPED_CACHE"):
        drop_path = f"{prefix}.pii_dropped.jsonl"
        dump_jsonl(globals()["_PII_DROPPED_CACHE"], drop_path)
        print(f"[INFO] dropped candidates: {len(globals()['_PII_DROPPED_CACHE'])}")
        print(f" - {drop_path}")
