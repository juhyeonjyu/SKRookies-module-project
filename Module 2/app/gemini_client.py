# gemini_client.py
import json
import re
import google.generativeai as genai

class GeminiStats:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def analyze(self, prompt: str) -> str:
        try:
            resp = self.model.generate_content(prompt)
            if resp and resp.candidates:
                return resp.candidates[0].content.parts[0].text.strip()
            return "분석 결과를 가져올 수 없습니다."
        except Exception as e:
            return f"Gemini 분석 오류: {str(e)}"

    def analyze_json(self, prompt: str):
        """반드시 JSON을 기대. 실패 시 None."""
        try:
            resp = self.model.generate_content(prompt)
            text = ""
            if resp and resp.candidates:
                text = resp.candidates[0].content.parts[0].text
            if not text:
                return None
            # ```json ... ``` 안/밖 JSON 추출
            m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
            raw = m.group(1) if m else text
            # 첫 { ... } 블럭만 파싱
            m2 = re.search(r"(\{.*\})", raw, flags=re.S)
            if not m2:
                return None
            return json.loads(m2.group(1))
        except Exception:
            return None


# 기존 텍스트 요약 프롬프트(유지)
DL_REGION_MAP = {
    "11": "서울","12": "부산","13": "경기","14": "강원","15": "충북","16": "충남",
    "17": "전북","18": "전남","19": "경북","20": "경남","21": "제주",
}

def prepare_prompt_from_stats(stats: dict, user_query: str) -> str:
    def format_section(title: str, data: dict) -> str:
        if not data:
            return f"[{title}] 데이터 없음"
        lines = [f"[{title}]"]
        for k, v in data.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    formatted_stats = []
    if "dl_prefix_counts" in stats:
        enriched = {f"{code} ({DL_REGION_MAP.get(code,'알 수 없는 지역')})": cnt
                    for code, cnt in stats["dl_prefix_counts"].items()}
        formatted_stats.append(format_section("운전면허 앞자리 코드 분포 (지역 포함)", enriched))
    if "email_domain_top10" in stats:
        formatted_stats.append(format_section("이메일 도메인 Top10", stats["email_domain_top10"]))
    if "phone_last_4_counts" in stats:
        formatted_stats.append(format_section("전화번호 뒷 4자리 빈도", stats["phone_last_4_counts"]))
    if "rrn_gender_counts" in stats:
        formatted_stats.append(format_section("주민번호 성별 분포", stats["rrn_gender_counts"]))
    if "rrn_full_birth_year_counts" in stats:
        formatted_stats.append(format_section("주민번호 전체 출생 연도 분포", stats["rrn_full_birth_year_counts"]))
    if "family_name_top10" in stats:
        formatted_stats.append(format_section("성씨 Top10", stats["family_name_top10"]))
    if "address_region_top10" in stats:
        formatted_stats.append(format_section("주소 지역(시/도) Top10", stats["address_region_top10"]))

    stats_text = "\n\n".join(formatted_stats)
    return f"""
너는 데이터 분석가다.
아래는 개인정보 데이터에서 사전 집계한 통계 요약이다:
{stats_text}

사용자의 요청: "{user_query}"

규칙:
- 반드시 제공된 통계값만 바탕으로 답변해라. 새로운 추측은 하지 마라.
- 주민번호: rrn_gender_counts / rrn_full_birth_year_counts 사용.
- 운전면허번호: dl_prefix_counts 사용.
- 이메일: email_domain_top10 사용.
- 전화번호: phone_last_4_counts 사용.
- 성씨: family_name_top10 사용.
- 주소: address_region_top10 사용.
- 불필요한 설명은 줄이고, 통계 수치와 간단한 해설만 제시하라.
"""

def prepare_planner_prompt(user_query: str, available_columns: list, known_regions: list) -> str:
    cols = ", ".join(available_columns)
    regs = ", ".join(sorted({r for r in known_regions if r})) or "(없음)"
    return f"""
당신은 '질문을 집계 계획(JSON)'으로 변환하는 플래너다.

사용자 질문: "{user_query}"

데이터프레임 컬럼: [{cols}]
region_first(주소 1토큰) 가능한 값(예시): [{regs}]

규칙:
- 질문에 위 지역 값(예: 서울, 부산, 경기 등)이 포함되어 있으면 filters에
  {{"column":"region_first","op":"eq","value":"해당지역"}}을 반드시 추가하라.
- 두 가지 의도가 같이 오면(예: 남녀 통계 + 나이별 남녀) 더 구체적인 의도(나이별 남녀)를 우선한다.
- 아래 스키마로만 JSON 응답. 해설 금지. 코드블록( ```json )으로 감싸도 좋다.

스키마:
{{
  "filters": [{{"column": "<컬럼명>", "op": "eq|contains|startswith|in|between", "value": "<값 또는 [값1,값2]>"}} ...],
  "groupby": ["<축1>", "<축2(선택)>"],
  "metrics": [{{"op": "count", "column": "*"}}],
  "chart": {{ "type": "bar|bar_grouped|pie|line", "x": "<x축>", "category": "<범례(선택)>" }},
  "limit": <정수 선택>
}}

예시1) "서울시 남녀 통계":
{{
  "filters": [{{"column":"region_first","op":"eq","value":"서울"}}],
  "groupby": ["gender"],
  "metrics": [{{"op":"count","column":"*"}}],
  "chart": {{"type":"bar","x":"gender"}},
  "limit": 50
}}

예시2) "서울시 나이별 남녀 통계":
{{
  "filters": [{{"column":"region_first","op":"eq","value":"서울"}}],
  "groupby": ["age_band","gender"],
  "metrics": [{{"op":"count","column":"*"}}],
  "chart": {{"type":"bar_grouped","x":"age_band","category":"gender"}},
  "limit": 100
}}

반드시 위 스키마에 맞는 JSON만 반환하라.
"""