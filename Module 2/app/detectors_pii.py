# detectors_pii.py
# 역할:
#  - 8종 PII(이름, 여권번호, 운전면허번호, 주민등록번호, 주소, 이메일, 연락처, 카드정보) 판별
#  - 필터 모듈에서 import하여 `classify_text(text, context)`로 사용
# 설계 원칙:
#  - 문자열 정규화 후 판정(제로폭 문자/다양한 대시/공백 정리)
#  - 이름(name)은 오탐 방지를 위해 "헤더 단서가 있을 때만" 판정 (표/엑셀용)
#  - 전화/이메일/주민/카드/여권/운전면허/주소는 패턴 + 라벨 힌트 병행
#
# context 예시:
#   {"header": "성명", "container": "page=1,table_1", "source_type": "pdf_table"}
#
# 반환값: {"name","passport","driver_license","rrn","address","email","phone","card"} 또는 None

import re
from typing import Optional, Dict

# ========= 텍스트 정규화 =========
_ZW_CHARS = dict.fromkeys(map(ord, ["\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"]), None)

def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = s.translate(_ZW_CHARS)  # zero-width 제거
    # 다양한 하이픈/대시를 ASCII '-'로 통일
    s = (s.replace("\u2010", "-")
           .replace("\u2011", "-")
           .replace("\u2012", "-")
           .replace("\u2013", "-")
           .replace("\u2014", "-"))
    # 공백 정리
    return " ".join(s.split())

# ========= 패턴 =========
EMAIL = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')

# 전화번호: 국내/국제/E.164 보조
KR_PHONE     = re.compile(r'(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)')
INTL_PHONE   = re.compile(r'(?<!\d)(?:\+82|00\s?82)[-\s]?1[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)')
E164_PHONE   = re.compile(r'(?<!\d)\+?\d{8,15}(?!\d)')

# 주민등록번호
RRN = re.compile(r'(?<!\d)\d{6}-?\d{7}(?!\d)')

# 카드번호(포맷 기반) - 실무에서는 Luhn 검증을 추가 권장
CARD_16   = re.compile(r'(?<!\d)(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})(?!\d)')
CARD_4_6_5= re.compile(r'(?<!\d)(\d{4})[-\s]?(\d{6})[-\s]?(\d{5})(?!\d)')

# 여권번호(보수적): 1~2문자 + 7~8숫자 (예: M1234567)
PASSPORT = re.compile(r'\b[A-Z]{1,2}\d{7,8}\b')

# 운전면허(한국): 12-34-567890-12 (하이픈 없는 12자리형은 라벨 있을 때만 허용)
KR_DL_HYPHEN    = re.compile(r'(?<!\d)\d{2}-\d{2}-\d{6}-\d{2}(?!\d)')
KR_DL_12_DIGITS = re.compile(r'(?<!\d)\d{12}(?!\d)')

# 주소(한국어 휴리스틱): 광역/시군구/도로명 계열 힌트
ADDR_HINT = re.compile(r'(대한민국|서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)')
ADDR_CORE = re.compile(r'(?=.*(시|군|구))(?=.*(동|읍|면|리|로|길|번길))')

# 이름(보수적): 2~4자 한글
HANGUL_NAME = re.compile(r'^[가-힣]{2,4}$')

# ========= 라벨(헤더) 힌트 =========
NAME_LABELS     = ('이름', '성명', '성 명', 'name', 'full name')
EMAIL_LABELS    = ('이메일', 'email', 'e-mail')
PHONE_LABELS    = ('연락처', '전화', '휴대폰', 'phone', 'tel')
ADDR_LABELS     = ('주소', 'address')
PASSPORT_LABELS = ('여권', 'passport')
DLABELS         = ('운전면허', 'driver', 'dl')
CARD_LABELS     = ('카드', '신용카드', 'card', 'pan')

# 이름 오탐 방지용(급여/세금/보험/항목/금액 등)
NON_NAME_HINTS = ("급여","항목","세","보험","수당","지원","금","연금","합계","공제","지급","식대","직위","소속")

def _has_label(context: Dict, labels) -> bool:
    h = (context.get('header') or '')
    h_low = h.lower()
    return any(lbl.lower() in h_low for lbl in labels)

def classify_text(text: str, context: Dict) -> Optional[str]:
    """
    요청 8종만 라벨링. 매칭 없으면 None.
    context: {"header": str, "container": str, "source_type": "xlsx"|"pdf_table"|"pdf_text"|...}
    """
    s = normalize_text(text)
    if not s:
        return None

    # ---- 이메일 ----
    if EMAIL.search(s) or (_has_label(context, EMAIL_LABELS) and '@' in s):
        return "email"

    # ---- 연락처(전화) ----
    if KR_PHONE.search(s) or INTL_PHONE.search(s):
        return "phone"
    if _has_label(context, PHONE_LABELS) and E164_PHONE.search(s):
        return "phone"

    # ---- 주민등록번호 ----
    if RRN.search(s):
        return "rrn"

    # ---- 카드 ----
    if CARD_16.search(s) or CARD_4_6_5.search(s):
        return "card"
    if _has_label(context, CARD_LABELS):
        digits = re.sub(r'\D', '', s)
        if 12 <= len(digits) <= 19:  # 느슨한 길이 조건
            return "card"

    # ---- 여권 ----
    if PASSPORT.search(s):
        return "passport"
    if _has_label(context, PASSPORT_LABELS) and re.search(r'[A-Z].*\d', s):
        return "passport"

    # ---- 운전면허 ----
    if KR_DL_HYPHEN.search(s):
        return "driver_license"
    if _has_label(context, DLABELS) and KR_DL_12_DIGITS.search(s):
        return "driver_license"

    # ---- 주소 ----
    if _has_label(context, ADDR_LABELS):
        return "address"
    if ADDR_HINT.search(s) and ADDR_CORE.search(s):
        return "address"

    # ---- 이름(표/엑셀에서 헤더가 성명/이름 계열일 때만) ----
    if _has_label(context, NAME_LABELS):
        # 블랙리스트 단어 포함 시 배제
        if not any(h in s for h in NON_NAME_HINTS):
            # 한글 2~4자 성명만 허용(로마자 이름은 용도에 따라 별도 확장)
            if HANGUL_NAME.match(s):
                return "name"

    # (옵션) 본문 텍스트(pdf_text)에서의 성명 판정이 필요하면 아래 주석을 해제
    # if context.get('source_type') == 'pdf_text' and HANGUL_NAME.match(s):
    #     if not any(h in s for h in NON_NAME_HINTS):
    #         return "name"

    return None

# ========== 간단 자가 테스트 ==========
if __name__ == "__main__":
    samples = [
        # 이메일
        ("user@test.co.kr", {"header":"이메일", "source_type":"xlsx"}),
        # 전화
        ("010-1234-5678", {"header":"연락처", "source_type":"xlsx"}),
        ("+82 10 1234 5678", {"header":"", "source_type":"pdf_text"}),
        # 주민등록번호
        ("900101-1234567", {"header":"", "source_type":"pdf_text"}),
        # 카드
        ("4111-1111-1111-1111", {"header":"", "source_type":"pdf_text"}),
        ("카드번호", {"header":"신용카드", "source_type":"pdf_table"}),
        # 여권
        ("M1234567", {"header":"", "source_type":"pdf_text"}),
        # 운전면허
        ("12-34-567890-12", {"header":"", "source_type":"pdf_text"}),
        ("123456789012", {"header":"운전면허", "source_type":"pdf_table"}),
        # 주소
        ("서울특별시 강남구 테헤란로 123", {"header":"주소", "source_type":"pdf_table"}),
        ("대한민국 서울시 강남구 역삼동 123-45", {"header":"", "source_type":"pdf_text"}),
        # 이름(헤더 있을 때만)
        ("홍길동", {"header":"성명", "source_type":"xlsx"}),
        # 이름 오탐 방지
        ("기본급여", {"header":"지급항목", "source_type":"pdf_table"}),
        ("건강보험", {"header":"공제항목", "source_type":"pdf_table"}),
    ]
    for t, ctx in samples:
        print(f"{t:>30}  | {ctx['header'] or '-':<8} | {ctx['source_type']:<9} -> {classify_text(t, ctx)}")
