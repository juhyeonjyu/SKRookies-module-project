# main.py
# 목적: 사용자의 자연어 질의 → 의도 추출 → 집계 → (선택) Gemini 요약 → ui.py로 구조화 결과 반환
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd

# (선택) 기존 모듈이 있다면 사용; 없으면 무시되고 로컬 집계만 수행됩니다.
try:
    from gemini_client import GeminiStats, prepare_prompt_from_stats  # optional
except Exception:
    GeminiStats = None
    prepare_prompt_from_stats = None


# -----------------------------
# 유틸: 파생 컬럼 생성
# -----------------------------
def _extract_gender_from_rrn(rrn: str) -> Optional[str]:
    if not isinstance(rrn, str) or not rrn:
        return None
    s = rrn.replace("-", "").strip()
    # YYMMDD + S + XXXXX
    if len(s) < 7 or not s[6].isdigit():
        return None
    code = s[6]
    if code in ("1", "3", "5", "7", "9"):  # 국내/외국인 코드 고려
        return "남"
    if code in ("2", "4", "6", "8", "0"):
        return "여"
    return None

def _extract_birth_year_from_rrn(rrn: str) -> Optional[int]:
    if not isinstance(rrn, str) or not rrn:
        return None
    s = rrn.replace("-", "").strip()
    if len(s) < 7 or not s[:2].isdigit() or not s[6].isdigit():
        return None
    yy = int(s[:2])
    gen = s[6]
    # 세기 추정
    if gen in ("1", "2", "5", "6", "9", "0"):  # 1900s
        century = 1900
    elif gen in ("3", "4", "7", "8"):          # 2000s
        century = 2000
    else:
        return None
    return century + yy

def _to_age_band(year: Optional[int]) -> Optional[str]:
    if not year:
        return None
    now_y = datetime.now().year
    age = max(0, now_y - year)
    band = (age // 10) * 10
    # 0~90대까지 라벨링
    if band >= 100:
        return "100s+"
    return f"{band}s"

def _address_region(addr: str) -> Optional[str]:
    if not isinstance(addr, str) or addr.strip() == "":
        return None
    tok = addr.strip().split()[0]
    # 약칭 정규화
    if tok.startswith("서울"):
        return "서울특별시"
    if tok.startswith("부산"):
        return "부산광역시"
    if tok.startswith("대구"):
        return "대구광역시"
    if tok.startswith("인천"):
        return "인천광역시"
    if tok.startswith("광주"):
        return "광주광역시"
    if tok.startswith("대전"):
        return "대전광역시"
    if tok.startswith("울산"):
        return "울산광역시"
    if tok.startswith("세종"):
        return "세종특별자치시"
    if tok.startswith("경기"):
        return "경기도"
    if tok.startswith("강원"):
        return "강원특별자치도" if "특별" in tok else "강원도"
    if tok.startswith("충북"):
        return "충청북도"
    if tok.startswith("충남"):
        return "충청남도"
    if tok.startswith("전북"):
        return "전북특별자치도" if "특별" in tok else "전라북도"
    if tok.startswith("전남"):
        return "전라남도"
    if tok.startswith("경북"):
        return "경상북도"
    if tok.startswith("경남"):
        return "경상남도"
    if tok.startswith("제주"):
        return "제주특별자치도"
    return tok  # 기타는 첫 토큰 그대로

def _prepare_dataframe(file_path: str) -> pd.DataFrame:
    df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    # 파생 컬럼
    df["gender"] = df.get("rrn", "").apply(_extract_gender_from_rrn)
    df["birth_year"] = df.get("rrn", "").apply(_extract_birth_year_from_rrn)
    df["age_band"] = df["birth_year"].apply(_to_age_band)
    # 주소 앞 토큰(시/도)
    df["region"] = df.get("address", "").apply(_address_region)
    # 안전한 결측 처리
    for c in ("gender", "age_band", "region"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    return df


# -----------------------------
# 의도(집계 계획) 보정 규칙
# -----------------------------
def _heuristic_intent_from_query(user_query: str) -> Dict[str, Any]:
    """
    LLM 플래너가 부정확하더라도 기본 의도를 추정해 보정용 힌트를 제공.
    """
    q = (user_query or "").strip().lower()

    wants_gender = any(k in q for k in ["남녀", "성별", "gender"])
    wants_age    = any(k in q for k in ["나이", "연령", "연령대", "age"])
    # 지역 감지
    region_hint: Optional[str] = None
    if "서울" in q:
        region_hint = "서울특별시"
    elif "부산" in q:
        region_hint = "부산광역시"
    # 필요 시 확장…

    groupby: List[str] = []
    if wants_age and wants_gender:
        groupby = ["age_band", "gender"]
    elif wants_gender:
        groupby = ["gender"]
    elif wants_age:
        groupby = ["age_band"]
    else:
        groupby = ["age_band"]  # 기본

    return {
        "filters": [{"column": "region", "op": "contains", "value": region_hint}] if region_hint else [],
        "groupby": groupby,
        "metric": {"agg": "count", "column": None},
        "chart_spec": {"chart_type": "bar_grouped" if len(groupby) == 2 else "bar",
                       "x": groupby[0],
                       "category": (groupby[1] if len(groupby) > 1 else None),
                       "y": "count",
                       "title": None}
    }


def _apply_filters(df: pd.DataFrame, filters: List[Dict[str, Any]]) -> pd.DataFrame:
    out = df
    for f in (filters or []):
        col = f.get("column")
        op = (f.get("op") or "").lower()
        val = f.get("value")
        if not col or col not in out.columns:
            continue
        if val in (None, ""):
            continue
        s = out[col].astype(str)
        if op == "contains":
            out = out[s.str.contains(str(val), na=False)]
        elif op == "eq":
            out = out[s == str(val)]
        elif op == "startswith":
            out = out[s.str.startswith(str(val), na=False)]
        elif op == "endswith":
            out = out[s.str.endswith(str(val), na=False)]
    return out


def _group_aggregate(df: pd.DataFrame, groupby: List[str]) -> pd.DataFrame:
    gb = [g for g in groupby if g in df.columns]
    if not gb:
        return pd.DataFrame(columns=["value"])
    agg_df = df.groupby(gb, dropna=False).size().reset_index(name="value")
    # 정렬: x, category 순
    if len(gb) == 2:
        agg_df = agg_df.sort_values([gb[0], gb[1]])
    else:
        agg_df = agg_df.sort_values(gb[0])
    return agg_df


def _to_chart_payload(agg_df: pd.DataFrame, groupby: List[str], title: Optional[str]) -> Dict[str, Any]:
    if len(groupby) == 2:
        x_col, cat_col = groupby
        data = [{"x": str(r[x_col]), "category": str(r[cat_col]), "value": int(r["value"])}
                for _, r in agg_df.iterrows()]
        spec = {"chart_type": "bar_grouped", "x": x_col, "category": cat_col, "y": "count",
                "title": title or f"{x_col} × {cat_col} 교차 집계"}
        return {"chart_data": data, "chart_spec": spec}
    else:
        x_col = groupby[0]
        data = [{"x": str(r[x_col]), "value": int(r["value"])} for _, r in agg_df.iterrows()]
        spec = {"chart_type": "bar", "x": x_col, "y": "count",
                "title": title or f"{x_col} 집계"}
        return {"chart_data": data, "chart_spec": spec}


def _summarize_text(agg_df: pd.DataFrame, groupby: List[str], region_hint: Optional[str]) -> str:
    if len(groupby) == 2 and set(groupby) == {"age_band", "gender"}:
        # 간단 요약
        total = int(agg_df["value"].sum())
        scope = f"{region_hint} " if region_hint else ""
        return f"{scope}연령대×성별 교차 집계 총 {total}건입니다."
    else:
        total = int(agg_df["value"].sum())
        return f"총 {total}건 집계되었습니다."


# -----------------------------
# 공개 함수: ui.py에서 호출
# -----------------------------
def run_llm_analysis(file_path: str, user_query: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    반환 형식(dict):
    {
      "analysis_text": "...",
      "chart_data": [...],
      "chart_spec": {...},
      "plan": {...}              # 디버깅용
    }
    """
    # 1) 데이터 로드(+파생)
    df = _prepare_dataframe(file_path)

    # 2) 의도(집계 계획) 추정/보정
    plan = _heuristic_intent_from_query(user_query)

    # 3) 필터 적용
    dfq = _apply_filters(df, plan.get("filters", []))

    # 4) 그룹 집계
    groupby = plan.get("groupby", [])
    agg_df = _group_aggregate(dfq, groupby)

    # 5) 차트 페이로드 변환
    payload = _to_chart_payload(agg_df, groupby, title=plan.get("chart_spec", {}).get("title"))

    # 6) 간단 텍스트 요약 (선택: Gemini 요약으로 대체 가능)
    region_hint = None
    for f in plan.get("filters", []):
        if f.get("column") == "region" and f.get("value"):
            region_hint = f.get("value")
    analysis_text = _summarize_text(agg_df, groupby, region_hint)

    # (선택) Gemini로 요약/설명 생성
    # if GeminiStats and prepare_prompt_from_stats and api_key:
    #     try:
    #         # 필요 시 사전 통계 만들고 프롬프트 생성/요약 추가
    #         gem = GeminiStats(api_key)
    #         analysis_text = analysis_text + "\n" + str(gem.analyze("..."))
    #     except Exception:
    #         pass

    result = {
        "analysis_text": analysis_text,
        "chart_data": payload["chart_data"],
        "chart_spec": payload["chart_spec"],
        "plan": plan
    }
    return result


if __name__ == "__main__":
    # 간단 CLI 테스트
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="converted CSV 경로")
    ap.add_argument("query", help="자연어 질문")
    args = ap.parse_args()
    out = run_llm_analysis(args.file, args.query, os.getenv("GEMINI_API_KEY", ""))
    print(out.get("analysis_text", ""))
