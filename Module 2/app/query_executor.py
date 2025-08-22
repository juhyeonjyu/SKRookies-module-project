# query_executor.py
from typing import Dict, List, Any, Tuple, Optional
import math
import re
import pandas as pd

# ------- 파생 특성 생성 -------
def enrich_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "address" in out.columns:
        out["region_first"] = out["address"].fillna("").astype(str).str.split().str[0]

    def _parse_rrn(s: str):
        s = (s or "").strip()
        m = re.match(r"^(\d{6})-?(\d)(\d{6})$", s)
        if not m:
            return {"gender": None, "birth_year": None, "birth_month": None, "age": None}
        b6, s1, _ = m.groups()
        yy = int(b6[:2]); mm = int(b6[2:4])
        if s1 in "12":
            year = 1900 + yy; gender = "남" if s1 == "1" else "여"
        elif s1 in "34":
            year = 2000 + yy; gender = "남" if s1 == "3" else "여"
        else:
            year = None; gender = None
        from datetime import date
        today = date.today()
        age = (today.year - year) if year else None
        return {"gender": gender, "birth_year": year, "birth_month": mm, "age": age}

    if "rrn" in out.columns:
        parsed = out["rrn"].fillna("").astype(str).map(_parse_rrn)
        out["gender"] = parsed.map(lambda d: d["gender"])
        out["birth_year"] = parsed.map(lambda d: d["birth_year"])
        out["birth_month"] = parsed.map(lambda d: d["birth_month"])
        out["age"] = parsed.map(lambda d: d["age"])

        def _age_band(a):
            if a is None or (isinstance(a, float) and math.isnan(a)): return None
            b = int(a) // 10 * 10
            return f"{b}s"
        out["age_band"] = out["age"].map(_age_band)

    if "driver_license" in out.columns:
        m = out["driver_license"].fillna("").astype(str).str.extract(r"^(\d{2})-")
        out["dl_region"] = m[0]

    if "email" in out.columns:
        out["email_domain"] = out["email"].fillna("").astype(str).str.extract(r"@(.+)$")[0]

    if "phone" in out.columns:
        nums = out["phone"].fillna("").astype(str).str.replace(r"\D", "", regex=True)
        out["phone_head3"] = nums.str[:3]
        out["phone_head2"] = nums.str[:2]

    if "passport" in out.columns:
        out["passport_head"] = out["passport"].fillna("").astype(str).str[0].str.upper()

    if "card" in out.columns:
        digits = out["card"].fillna("").astype(str).str.replace(r"\D", "", regex=True)
        out["card_bin4"] = digits.str[:4]

    if "name" in out.columns:
        out["family_name"] = out["name"].fillna("").astype(str).str[0]

    return out


# ------- 플랜 실행 -------
def _apply_filter(df: pd.DataFrame, flt: Dict[str, Any]) -> pd.DataFrame:
    col = flt.get("column")
    op = flt.get("op")
    val = flt.get("value")
    if col not in df.columns:
        return df.iloc[0:0]  # unknown column → empty

    s = df[col].astype(str)
    if op == "eq":
        return df[s == str(val)]
    if op == "contains":
        return df[s.str.contains(str(val), na=False)]
    if op == "startswith":
        return df[s.str.startswith(str(val), na=False)]
    if op == "in" and isinstance(val, list):
        return df[s.isin([str(x) for x in val])]
    if op == "between" and isinstance(val, list) and len(val) == 2:
        try:
            v1, v2 = float(val[0]), float(val[1])
            return df[(pd.to_numeric(df[col], errors="coerce") >= v1) &
                      (pd.to_numeric(df[col], errors="coerce") <= v2)]
        except Exception:
            return df.iloc[0:0]
    return df


def execute_plan(df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
    dfe = enrich_df(df)

    # 1) 필터
    filters = plan.get("filters") or []
    for flt in filters:
        dfe = _apply_filter(dfe, flt)

    # 2) 그룹바이
    groupby = plan.get("groupby") or []
    if not groupby:  # 그룹 지정 없으면 전체 count
        cnt = len(dfe)
        return {
            "analysis_text": f"전체 건수: {cnt}",
            "chart_data": [{"x": "all", "value": int(cnt)}],
            "chart_spec": {"chart_type": "bar", "x": "x", "agg": "count"},
        }

    # 3) metrics: count만 지원
    # pivot or value_counts
    if len(groupby) == 1:
        key = groupby[0]
        counts = dfe[key].fillna("(빈값)").astype(str).value_counts()
        rows = [{"x": k, "value": int(v)} for k, v in counts.items()]
        spec = plan.get("chart") or {"type": "bar", "x": key}
        ctype = spec.get("type", "bar")
        chart_spec = {"chart_type": ctype, "x": key, "agg": "count"}
        return {
            "analysis_text": f"{key}별 건수 상위 {len(rows)}",
            "chart_data": rows,
            "chart_spec": chart_spec,
        }

    # 2축 그룹 → 그룹형 막대
    key1, key2 = groupby[0], groupby[1]
    pt = dfe.pivot_table(index=key1, columns=key2, values=dfe.columns[0], aggfunc="count", fill_value=0)
    rows = []
    for x, row in pt.iterrows():
        for cat, v in row.items():
            rows.append({"x": str(x), "value": int(v), "category": str(cat)})
    spec = plan.get("chart") or {"type": "bar_grouped", "x": key1, "category": key2}
    chart_spec = {"chart_type": spec.get("type", "bar_grouped"),
                  "x": spec.get("x", key1),
                  "category": spec.get("category", key2),
                  "agg": "count"}
    return {
        "analysis_text": f"{key1}×{key2} 교차 집계",
        "chart_data": rows,
        "chart_spec": chart_spec,
    }
