# visualizer.py
# 마스킹 직후/세부 분포 시각화 유틸

from typing import List, Tuple, Dict, Any, Iterable
import re
from collections import Counter, defaultdict
import matplotlib.pyplot as plt

# ----- 한글 폰트 안전 설정 -----
def _safe_set_korean_font():
    try:
        import matplotlib.font_manager as fm
        names = [f.name for f in fm.fontManager.ttflist]
        if "Malgun Gothic" in names:
            plt.rcParams["font.family"] = "Malgun Gothic"
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass
_safe_set_korean_font()

# ---------- 공통 그리기 ----------
def _bar_fig(title: str, labels: Iterable, values: Iterable, figsize=(9, 5)) -> Tuple[str, plt.Figure]:
    fig, ax = plt.subplots(figsize=figsize)
    x = list(labels)
    y = list(values)
    ax.bar(x, y)
    ax.set_title(title)
    ax.set_ylabel("빈도")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return title, fig

# ---------- (A) 마스킹 직후: 선택 항목별 건수 ----------
def create_quick_masking_fig(type_counts: Dict[str, int]) -> Tuple[str, plt.Figure]:
    title = "선택된 PII 항목별 마스킹 건수"
    return _bar_fig(title, type_counts.keys(), type_counts.values(), figsize=(8, 4.8))

# ---------- (B) 타입별 세부 분포(요구 사양) ----------
# 운전면허 지역 코드 → 명칭(선택)
DL_REGION_MAP = {
    "11": "서울", "12": "부산", "13": "경기", "14": "강원", "15": "충북",
    "16": "충남", "17": "전북", "18": "전남", "19": "경북", "20": "경남", "21": "제주",
}

_rrn_re = re.compile(r"^(\d{6})-?(\d)\*{6}$")  # mask_rrn 규칙: 123456-1******

def _first_digits(s: str, k: int) -> str:
    d = "".join(ch for ch in s if ch.isdigit())
    return d[:k] if d else ""

def _rrn_breakdown(text: str):
    """년/월/성별 추출 (마스킹 규칙: YYMMDD-g****** 유지)"""
    m = _rrn_re.match(text.strip())
    if not m:
        return None
    yymmdd, gender = m.groups()
    yy = int(yymmdd[0:2])
    mm = yymmdd[2:4]
    # 성별 코드: 1,2(1900대), 3,4(2000대)
    if gender in ("1", "2"):
        yyyy = 1900 + yy
    elif gender in ("3", "4"):
        yyyy = 2000 + yy
    else:
        return None
    sex = "남" if gender in ("1", "3") else "여"
    return yyyy, mm, sex

def create_pii_breakdown_figs(masked_records: List[Dict[str, Any]], top_n: int = 15) -> List[Tuple[str, plt.Figure]]:
    """
    요구한 규칙으로 세부 분포를 생성:
      - 이름: 성씨(첫 글자)
      - 연락처: 앞자리 2~3자리(여기선 3자리로 통일)
      - 주소: 맨 앞 단어
      - 이메일: 도메인
      - 주민번호: 연도별, 달별, 성별
      - 여권번호: 맨앞 M/S(대문자 기준), 그 외 OTHER
      - 면허번호: 지역번호(앞 2자리)
      - 카드번호: 맨앞 4자리
    입력은 마스킹 적용 후 레코드 리스트(각 항목에 최소 'pii_type','text' 존재).
    """
    figs: List[Tuple[str, plt.Figure]] = []
    by_type = defaultdict(list)
    for r in masked_records:
        t = (r.get("pii_type") or "").lower()
        txt = (r.get("text") or "").strip()
        if t and txt:
            by_type[t].append(txt)

    # 이름: 성씨(첫 글자)
    if by_type.get("name"):
        fam = [s[0] for s in by_type["name"] if len(s) >= 1]
        c = Counter(fam)
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("이름 · 성씨(첫 글자) 분포", labels, values))

    # 연락처: 앞 3자리
    if by_type.get("phone"):
        lead3 = [_first_digits(s, 3) for s in by_type["phone"]]
        c = Counter([x for x in lead3 if x])
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("연락처 · 앞 3자리 분포", labels, values))

    # 주소: 맨 앞 단어
    if by_type.get("address"):
        first_tok = [s.split()[0] for s in by_type["address"] if s.split()]
        c = Counter(first_tok)
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("주소 · 첫 단어 분포", labels, values))

    # 이메일: 도메인
    if by_type.get("email"):
        doms = [s.split("@", 1)[1] for s in by_type["email"] if "@" in s]
        c = Counter(doms)
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("이메일 · 도메인 분포", labels, values))

    # 주민번호: 연도/월/성별
    if by_type.get("rrn"):
        yrs, months, sexes = [], [], []
        for s in by_type["rrn"]:
            parsed = _rrn_breakdown(s)
            if parsed:
                y, m, sex = parsed
                yrs.append(str(y))
                months.append(m)          # "01"~"12"
                sexes.append(sex)         # 남/여
        if yrs:
            c = Counter(yrs)
            labels, values = zip(*c.most_common())  # 전체 연도
            figs.append(_bar_fig("주민번호 · 출생 연도 분포", labels, values))
        if months:
            c = Counter(months)
            labels = [f"{m}월" for m, _ in sorted(c.items(), key=lambda x: x[0])]
            values = [c[m[:-1]] if m.endswith("월") else c[m] for m in labels]  # 정렬용
            figs.append(_bar_fig("주민번호 · 출생 월 분포", labels, values))
        if sexes:
            c = Counter(sexes)
            labels, values = zip(*c.most_common())
            figs.append(_bar_fig("주민번호 · 성별 분포", labels, values))

    # 여권번호: 맨앞 M/S 구분
    if by_type.get("passport"):
        head = []
        for s in by_type["passport"]:
            ch = s.strip()[:1].upper()
            head.append(ch if ch in ("M", "S") else "OTHER")
        c = Counter(head)
        labels, values = zip(*c.most_common()) if c else ([], [])
        if labels:
            figs.append(_bar_fig("여권번호 · 앞자리 구분(M/S/기타)", labels, values))

    # 면허번호: 지역번호(앞 2자리)
    if by_type.get("driver_license"):
        region = []
        for s in by_type["driver_license"]:
            m = re.match(r"^(\d{2})-", s)
            if m:
                code = m.group(1)
                region.append(f"{code}({DL_REGION_MAP.get(code,'기타')})")
        c = Counter(region)
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("운전면허 · 지역번호(앞 2자리)", labels, values))

    # 카드번호: 앞 4자리
    if by_type.get("card"):
        head4 = []
        for s in by_type["card"]:
            m = re.match(r"^(\d{4})", s.replace(" ", "").replace("-", ""))
            if m:
                head4.append(m.group(1))
        c = Counter(head4)
        labels, values = zip(*c.most_common(top_n)) if c else ([], [])
        if labels:
            figs.append(_bar_fig("카드번호 · 앞 4자리", labels, values))

    return figs
