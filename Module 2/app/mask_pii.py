# mask_pii.py
# 역할:
#  - filter 단계 산출(.pii.jsonl/.pii.csv)을 입력으로 받아 선택된 PII 타입만 마스킹
#  - 출력 모드:
#       both        : 원문 text + masked_text 모두 출력(기본)
#       masked_only : 원문 text 제거, masked_text만 출력
#       replace     : text 컬럼을 마스킹 값으로 교체(masked_text 없음)
# 안전장치:
#  - 행수 보전: 입력 행수 == 출력 행수 (불일치 시 RuntimeError)
#  - ID 무결성 검사: 입력/출력의 ID(또는 대체키) 비교, mismatch 시 디버그 파일 생성
#
# 사용 예:
#   python mask_pii.py test_data_100.pii.jsonl --types all --output replace
#   python mask_pii.py test_data_100.pii.csv   --types name,email --output masked_only
#   python mask_pii.py test_data_100.pii.csv   --types all --out-prefix C:\out\test_data_100

import argparse, csv, json, re
from pathlib import Path
from typing import Dict, Iterable, List, Set

# --- 입력 스키마(필터 산출물) ---
KEYS_IN = ["id","pii_type","source_path","source_type","container","row","col","header","bbox","text"]

# ---------- 공통 I/O ----------
def iter_jsonl(path: str) -> Iterable[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                yield json.loads(s)

def dump_jsonl(records: List[Dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def dump_csv(records: List[Dict], out_path: str, output_mode: str):
    # 필드 결정
    if not records:
        if output_mode == "replace":
            fieldnames = KEYS_IN
        elif output_mode == "masked_only":
            fieldnames = [k for k in KEYS_IN if k != "text"] + ["masked_text"]
        else:
            fieldnames = KEYS_IN + ["masked_text"]
    else:
        fieldnames = list(records[0].keys())

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            row = dict(r)
            # bbox가 list/dict면 문자열 직렬화
            if isinstance(row.get("bbox"), (list, dict)):
                row["bbox"] = json.dumps(row["bbox"], ensure_ascii=False)
            w.writerow({k: row.get(k, "") for k in fieldnames})

# ---------- 마스킹 도우미 ----------
def mask_keep_prefix(s: str, keep: int, mask_char: str="*") -> str:
    if s is None: return s
    if len(s) <= keep: return s
    return s[:keep] + (mask_char * (len(s)-keep))

def mask_digits_keep_last(s: str, last_keep: int, mask_char: str="*") -> str:
    out, seen = [], 0
    digits = [ch for ch in s if ch.isdigit()]
    n = len(digits)
    for ch in s:
        if ch.isdigit():
            seen += 1
            if seen <= n - last_keep:
                out.append(mask_char)
            else:
                out.append(ch)
        else:
            out.append(ch)
    return "".join(out)

def mask_digits_keep_first(s: str, first_keep: int, mask_char: str="*") -> str:
    out, kept = [], 0
    for ch in s:
        if ch.isdigit():
            if kept < first_keep:
                out.append(ch); kept += 1
            else:
                out.append(mask_char)
        else:
            out.append(ch)
    return "".join(out)

# ---------- PII 타입별 마스킹 ----------
# 1) 이름: 홍길동 → 홍*동 (2자는 홍*)
def mask_name(text: str) -> str:
    if not text: return text
    t = text.strip()
    if len(t) <= 1: return t
    if len(t) == 2: return t[0] + "*"
    return t[0] + "*" * (len(t)-2) + t[-1]

# 2) 여권번호: 앞 5글자 보존
def mask_passport(text: str) -> str:
    if not text: return text
    t = text.strip()
    keep = 5 if len(t) > 5 else len(t)
    return t[:keep] + "*" * (len(t)-keep)

# 3) 운전면허(한국 12-34-XXXXXX-YY): 12-34-0*****-**
def mask_driver_license(text: str) -> str:
    if not text: return text
    t = text.strip()
    m = re.match(r'^(\d{2})-(\d{2})-(\d{6})-(\d{2})$', t)
    if m:
        g1, g2, g3, g4 = m.groups()
        g3m = g3[0] + "*" * 5
        g4m = "**"
        return f"{g1}-{g2}-{g3m}-{g4m}"
    # 포맷 불일치 폴백: 숫자 뒤 3자리만 보존
    return mask_digits_keep_last(t, 3)

# 4) 주민등록번호: 123456-1******
def mask_rrn(text: str) -> str:
    if not text: return text
    t = text.strip()
    m = re.match(r'^(\d{6})-?(\d)(\d{6})$', t)
    if m:
        b6, s1, _tail6 = m.groups()
        return f"{b6}-{s1}{'*'*6}"
    return mask_digits_keep_first(t, 7)  # 근사 폴백

# --- 주소 마스킹(시·군/구까지 보존) ---
ADM_SUFFIX = ("시", "군", "구")

def _mask_korean_address_segment(seg: str) -> str:
    """
    규칙:
      - 토큰을 공백 기준으로 분리
      - 첫번째 '시/군/구' 토큰 위치 idx1, 두번째 '시/군/구' 토큰 위치 idx2를 찾음
      - idx2가 있으면 idx2 이후 토큰부터 마스킹
      - idx2가 없으면 idx1 이후 토큰부터 마스킹
      - 구분자(쉼표/세미콜론)는 상위 함수에서 보존
    """
    seg = (seg or "").strip()
    if not seg:
        return seg

    tokens = seg.split()
    idx1, idx2 = None, None
    for i, tok in enumerate(tokens):
        if tok.endswith(ADM_SUFFIX):
            if idx1 is None:
                idx1 = i
            elif idx2 is None:
                idx2 = i
                break

    if idx1 is None:
        start_mask = None  # '시/군/구'가 전혀 없으면 마스킹 시작점 없음(원문 유지)
    elif idx2 is not None:
        start_mask = idx2 + 1
    else:
        start_mask = idx1 + 1

    out = []
    for i, tok in enumerate(tokens):
        if start_mask is not None and i >= start_mask:
            masked = "".join("*" if (ch.isdigit() or ('가' <= ch <= '힣')) else ch for ch in tok)
            out.append(masked)
        else:
            out.append(tok)
    return " ".join(out)

def mask_address(text: str) -> str:
    """
    세그먼트 분리: 쉼표/세미콜론(/) 기준. 각 세그먼트에 위 규칙 적용.
    예)
      "인천시 미추홀구 용현동 123-45"     -> "인천시 미추홀구 ******"
      "성남시 분당구 정자동 12"           -> "성남시 분당구 **"
      "성남시 정자동 12"                  -> "성남시 **"
      "서울특별시 강남구 테헤란로 123"     -> "서울특별시 강남구 ******"
      "경기도 성남시 분당구 정자동 1-2"   -> "경기도 성남시 분당구 ******"
    """
    if not text: return text
    parts = re.split(r'([,;/])', text)  # 구분자 보존
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:  # 실제 세그먼트
            out.append(_mask_korean_address_segment(part))
        else:           # 구분자
            out.append(part)
    return "".join(out)

# 6) 이메일: 로컬파트 앞 2글자 보존
def mask_email(text: str) -> str:
    if not text: return text
    t = text.strip()
    if "@" not in t: return t
    local, domain = t.split("@", 1)
    if len(local) <= 2:
        masked_local = local
    else:
        masked_local = local[:2] + "*" * (len(local)-2)
    return f"{masked_local}@{domain}"

# 7) 연락처: 앞 3자리 + 뒤 4자리 보존
def mask_phone(text: str) -> str:
    if not text:
        return text

    digits = [c for c in text if c.isdigit()]
    n = len(digits)
    if n <= 7:
        return text  # 너무 짧으면 그대로 반환

    # 앞 3자리 + 뒤 4자리 보존, 나머지는 *
    masked_digits = (
        digits[:3] + ["*"] * (n - 7) + digits[-4:]
    )

    # 원래 포맷(하이픈 등)은 유지
    out = []
    di = 0
    for c in text:
        if c.isdigit():
            out.append(masked_digits[di])
            di += 1
        else:
            out.append(c)
    return "".join(out)


# 8) 카드:
#   - 4-4-4-4 : g1-g2-g3-g4 → g1-(g2 앞2)**-****-*(g4 뒤3)
#   - 4-6-5   : g1-g2-g3     → g1-(g2 앞2)****-*(g3 뒤3)
def mask_card(text: str) -> str:
    if not text: return text
    t = text.strip()
    m1 = re.match(r'^(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})$', t)
    if m1:
        g1, g2, g3, g4 = m1.groups()
        g2m = g2[:2] + "**"
        g3m = "****"
        g4m = "*" + g4[-3:]
        return f"{g1}-{g2m}-{g3m}-{g4m}"
    m2 = re.match(r'^(\d{4})[-\s]?(\d{6})[-\s]?(\d{5})$', t)
    if m2:
        g1, g2, g3 = m2.groups()
        g2m = g2[:2] + "*" * 4
        g3m = "*" * (len(g3)-3) + g3[-3:]
        return f"{g1}-{g2m}-{g3m}"
    return mask_digits_keep_last(t, 3)

# ---------- 라우터 ----------
MASKERS = {
    "name": mask_name,
    "passport": mask_passport,
    "driver_license": mask_driver_license,
    "rrn": mask_rrn,
    "address": mask_address,
    "email": mask_email,
    "phone": mask_phone,
    "card": mask_card,
}

def apply_mask(pii_type: str, text: str) -> str:
    fn = MASKERS.get((pii_type or "").lower())
    return fn(text) if fn else text

def parse_types(s: str) -> Set[str]:
    s = (s or "").strip().lower()
    if s in ("all", "*"):
        return set(MASKERS.keys())
    items = [x.strip().lower() for x in s.split(",") if x.strip()]
    return {x for x in items if x in MASKERS}

# ---------- 핵심 처리 ----------
def process(records: List[Dict], enabled: Set[str], output_mode: str) -> List[Dict]:
    """
    - 어떤 타입을 선택하더라도 '행 삭제 없음'을 보장
    - output_mode에 따라 컬럼 구성 변경
    """
    out = []
    for r in records:
        t = (r.get("pii_type") or "").lower()
        txt = r.get("text","")
        masked = apply_mask(t, txt) if t in enabled else txt

        if output_mode == "both":
            o = dict(r)
            o["masked_text"] = masked
        elif output_mode == "masked_only":
            o = {k: r.get(k, "") for k in KEYS_IN if k != "text"}  # 원문 제거
            o["masked_text"] = masked
        elif output_mode == "replace":
            o = dict(r)
            o["text"] = masked
            o.pop("masked_text", None)
        else:
            raise ValueError("invalid output_mode")
        out.append(o)

    # 행수 보전 검증
    if len(out) != len(records):
        raise RuntimeError(f"[BUG] output rows {len(out)} != input rows {len(records)}")
    return out

def build_id_list(lst: List[Dict]) -> List[str]:
    """ID가 없으면 대체키 생성 (source_path|container|row|col|pii_type|text)."""
    res = []
    for r in lst:
        rid = r.get("id")
        if not rid:
            rid = f"{r.get('source_path','')}|{r.get('container','')}|{r.get('row','')}|{r.get('col','')}|{(r.get('pii_type') or '').lower()}|{r.get('text','')}"
        res.append(str(rid))
    return res

# ---------- CLI ----------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Mask selected PII types in .pii.jsonl/.pii.csv (row-preserving)")
    ap.add_argument("pii_file", help=".pii.jsonl or .pii.csv (filter 결과)")
    ap.add_argument("--types", default="all",
                    help="마스킹 대상: all | comma list (예: name,email,phone)")
    ap.add_argument("--output", choices=["both","masked_only","replace"], default="both",
                    help="출력 형식: both(기본) | masked_only(원문 제거) | replace(text를 마스킹값으로 교체)")
    ap.add_argument("--out-prefix", default="", help="출력 prefix (기본: 입력 파일명 기준)")
    args = ap.parse_args()

    p = Path(args.pii_file)
    if not p.exists():
        raise SystemExit(f"입력 경로 없음: {p}")

    enabled = parse_types(args.types)
    if not enabled:
        raise SystemExit("유효한 --types 가 없습니다. (가능: name,passport,driver_license,rrn,address,email,phone,card | all)")

    # 입력 로딩
    suffix = p.suffix.lower()
    if suffix == ".jsonl":
        records = list(iter_jsonl(str(p)))
    elif suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(str(p), dtype=str, keep_default_na=False)
        records = []
        for _, x in df.iterrows():
            rec = {k: x.get(k, "") for k in df.columns}
            # bbox 문자열이면 JSON 파싱 시도
            if "bbox" in rec:
                s = (rec["bbox"] or "").strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        rec["bbox"] = json.loads(s)
                    except Exception:
                        pass
            records.append(rec)
    else:
        raise SystemExit("지원 입력: .jsonl 또는 .csv")

    # 처리
    out_records = process(records, enabled, args.output)

    # ===== ID 무결성 검사 & 디버그 =====
    in_ids  = build_id_list(records)
    out_ids = build_id_list(out_records)

    missing_in_out = [i for i in in_ids if i not in out_ids]
    extra_in_out   = [i for i in out_ids if i not in in_ids]

    dbg_base = args.out_prefix or p.with_suffix("").as_posix().replace(".pii","")
    if missing_in_out or extra_in_out:
        # 디버그 파일 덤프
        with open(f"{dbg_base}.mask_debug_in_ids.txt","w",encoding="utf-8") as f:
            f.write("\n".join(in_ids))
        with open(f"{dbg_base}.mask_debug_out_ids.txt","w",encoding="utf-8") as f:
            f.write("\n".join(out_ids))
        with open(f"{dbg_base}.mask_debug_diff.txt","w",encoding="utf-8") as f:
            f.write("[missing_in_out]\n"); f.write("\n".join(missing_in_out)); f.write("\n\n")
            f.write("[extra_in_out]\n");   f.write("\n".join(extra_in_out));   f.write("\n")
        print(f"[WARN] ID mismatch: missing={len(missing_in_out)}, extra={len(extra_in_out)}")
        print(f"       Debug dumps: {dbg_base}.mask_debug_*.txt")

    # 출력 파일명
    suffix_tag = {"both":"masked", "masked_only":"masked_only", "replace":"masked_replace"}[args.output]
    out_jsonl = f"{dbg_base}.{suffix_tag}.jsonl"
    out_csv   = f"{dbg_base}.{suffix_tag}.csv"

    # 저장(덮어쓰기)
    dump_jsonl(out_records, out_jsonl)
    dump_csv(out_records, out_csv, args.output)

    # 요약
    print(f"[OK] masked rows: {len(out_records)}  (input rows: {len(records)})")
    print(f" - {out_jsonl}")
    print(f" - {out_csv}")
