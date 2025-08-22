# llm_charting.py
from __future__ import annotations
import json
from typing import Any, Dict, Optional, Tuple, List
import matplotlib.pyplot as plt
import pandas as pd

# --------- 프롬프트 보강 ---------
def json_chart_spec_instructions() -> str:
    return """
당신의 최종 출력은 반드시 JSON 하나여야 한다. 다른 텍스트를 덧붙이지 마라.
스키마:
{
  "analysis_text": "간결한 해설(한국어)",
  "chart_data": [{"x": "<범주/라벨>", "value": <수치>} , ...],
  "chart_spec": {
    "chart_type": "bar|line|pie",   // 생략 시 bar
    "x": "<x축 라벨>",               // 선택
    "y": "<y축 라벨 또는 집계명>",    // 선택(없으면 'count')
    "title": "<차트 제목>"            // 선택
  }
}

제약:
- JSON 외 설명/코드는 절대 출력하지 마라.
- 숫자는 number 타입으로 표현하라(문자열 금지).
"""

# --------- 응답 파서 ---------
def parse_llm_chart_payload(text: str) -> Optional[Dict[str, Any]]:
    """
    LLM 응답 텍스트에서 JSON을 찾아 파싱한다.
    ```json ... ``` 로 감싸져 있든, 생 텍스트 JSON이든 모두 지원.
    """
    if not text:
        return None

    s = text.strip()

    # fenced code block 제거
    if s.startswith("```"):
        # ```json\n ... \n```
        first = s.find("\n")
        if first != -1:
            s = s[first+1:]
        if s.endswith("```"):
            s = s[:-3].strip()

    # 바깥에 설명 텍스트가 섞인 경우, 첫 '{' ~ 마지막 '}' 범위를 잡는다
    try:
        l = s.index("{")
        r = s.rindex("}")
        s = s[l:r+1]
    except ValueError:
        pass

    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and ("chart_data" in obj or "analysis_text" in obj):
            return obj
    except Exception:
        return None
    return None

# --------- Matplotlib 렌더 ---------
def render_chart(chart_data: List[Dict[str, Any]], chart_spec: Dict[str, Any]) -> Optional[plt.Figure]:
    """
    chart_data 포맷
      - 단일계열: [{"x": "...", "value": number}, ...]
      - 다중계열(그룹): [{"x":"...", "category":"남", "value": number}, ...]

    chart_spec 예
      - {"chart_type":"bar", "x":"age_band", "y":"count", "title":"..."}
      - {"chart_type":"bar_grouped", "x":"age_band", "category":"gender", "y":"count", "title":"..."}
      - {"chart_type":"line"| "pie", ...}  (기존과 동일)
    """
    if not chart_data:
        return None

    spec = chart_spec or {}
    ctype = (spec.get("chart_type") or "bar").lower()
    title = spec.get("title") or "LLM-Requested Chart"
    x_label = spec.get("x") or ""
    y_label = spec.get("y") or "count"

    # ---- 그룹 막대 지원 ----
    if ctype == "bar_grouped":
        df = pd.DataFrame(chart_data)
        # 기대 컬럼: x, category, value
        if not {"x", "category", "value"}.issubset(df.columns):
            return None
        df["x"] = df["x"].astype(str)
        df["category"] = df["category"].astype(str)
        # pivot → 그룹 막대
        pv = df.pivot(index="x", columns="category", values="value").fillna(0)
        fig, ax = plt.subplots()
        pv.plot(kind="bar", ax=ax)
        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.legend(title=spec.get("category") or "category", loc="best")
        for tick in ax.get_xticklabels():
            tick.set_rotation(45)
            tick.set_ha("right")
        fig.tight_layout()
        return fig

    # ---- 기존 단일계열 처리 ----
    xs = [str(d.get("x", "")) for d in chart_data]
    ys = []
    for d in chart_data:
        v = d.get("value", 0)
        try:
            ys.append(float(v))
        except Exception:
            return None

    fig, ax = plt.subplots()
    if ctype == "line":
        ax.plot(xs, ys, marker="o")
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
    elif ctype == "pie":
        ax.pie(ys, labels=xs, autopct="%1.1f%%")
        ax.axis("equal")
    else:  # 기본 bar
        ax.bar(xs, ys)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)

    ax.set_title(title)
    if ctype != "pie":
        for tick in ax.get_xticklabels():
            tick.set_rotation(45)
            tick.set_ha("right")
    fig.tight_layout()
    return fig