# ui.py
# 실행: streamlit run ui.py
API_KEY_FALLBACK = "[Gemini API 키를 발급 받아주세요.]"  # 환경변수(GEMINI_API_KEY) 사용 권장

import os
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ---- 코어 모듈 (동일 venv/프로젝트 폴더에 있어야 함) ----
import agent  # run_agent_on_paths
from mask_pii import process as mask_process
from xlsx_apply_mask import apply_masks_to_workbook
from convert import convert_csv_format

# 시각화 유틸
from visualizer import create_quick_masking_fig, create_pii_breakdown_figs
from llm_charting import render_chart

# LLM 파이프라인
try:
    from main import run_llm_analysis  # def run_llm_analysis(file_path, user_query, api_key) -> str|dict
except Exception:
    run_llm_analysis = None

# Matplotlib Figure -> png(base64)
import io, base64

def fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=144)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{data}"

# ------------------------
# 페이지/테마 설정
# ------------------------
st.set_page_config(page_title="PII Masking Dashboard", page_icon="🧩", layout="wide")

# ------------------------
# 색상/스타일
# ------------------------
PRIMARY = "#000060"
TEXT_MUTED = "#6B7280"
BORDER = "#E5E7EB"
CARD_BG = "#FFFFFF"
PINK_BAR = "#F8E4E8"

CSS = f"""
    body, .main .block-container {{ background:white; }}
    .main .block-container {{ padding-top: 0.2rem; padding-bottom: 1rem; }}
    .hero {{color:{PRIMARY}; padding:5px 18px; border-bottom-left-radius:14px; border-bottom-right-radius:14px;}}
    .hero .title {{ font-weight:800; font-size:3.4rem; letter-spacing:-.02em; margin-top:-2.6rem}}
    .hero .subtitle-line {{ margin-top:.4rem; height:4px; background:rgba(255,255,255,.55); border-radius:4px; margin-bottom:2rem;}}
    .card {{ border:1px solid {BORDER}; background:{CARD_BG}; border-radius:14px; padding:14px 16px; box-shadow:0 1px 2px rgba(0,0,0,.03); }}
"""
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

# ------------------------
# 세션 상태
# ------------------------
ss = st.session_state
ss.setdefault("masking_done", False)
ss.setdefault("messages", [])                 # 채팅 로그 (렌더는 맨 아래 공통 루프에서만)
ss.setdefault("last_file_name", None)
ss.setdefault("process_steps", [])
ss.setdefault("process_complete", False)
ss.setdefault("processed_bytes", b"")
ss.setdefault("processed_filename", "")
ss.setdefault("workdir", "")
ss.setdefault("out_masked_csv", "")          # agent+mask 이후 masked_replace.csv
ss.setdefault("out_converted_csv", "")       # convert 이후 CSV
ss.setdefault("llm_ready", False)
ss.setdefault("last_llm_result", None)       # run_llm_analysis 반환값(텍스트/딕셔너리)
ss.setdefault("last_chart_payload", None)    # {'chart_data':..., 'chart_spec':...}
ss.setdefault("masked_type_counts", {})      # {'email': n, ...}
ss.setdefault("masked_records", [])          # 마스킹된 레코드 전체(선택 타입 포함)
ss.setdefault("enabled_types", set())        # 사용자가 체크한 PII 타입(내부코드)

# ------------------------
# 헤더
# ------------------------
st.markdown(
    f"""
    <div class='hero'>
      <div class='title'>PII Masking Dashboard 📎</div>
      <div class='subtitle-line'>안전하게 개인정보를 처리하고 Gemini와 함께 인사이트를 비즈니스에 활용해 보세요.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------
# 한글 → 내부 타입 매핑
# ------------------------
KOR2TYPE = {
    "이름": "name",
    "주민번호": "rrn",
    "연락처": "phone",
    "여권번호": "passport",
    "주소": "address",
    "면허번호": "driver_license",
    "이메일": "email",
    "카드번호": "card",
}

# ------------------------
# 사이드바
# ------------------------
with st.sidebar:
    st.markdown("### 💾 파일 업로드")
    uploaded_file = st.file_uploader("마스킹이 필요한 파일을 올려주세요.", type=["xlsx"])
    if uploaded_file is not None:
        st.caption(uploaded_file.name)

    st.markdown("### 📍 개인정보 마스킹 선택")
    pii_options = list(KOR2TYPE.keys())
    selected_options = []
    for i in range(0, len(pii_options), 2):
        cols = st.columns(2, gap="small")
        for col, opt in zip(cols, pii_options[i:i+2]):
            with col:
                if st.checkbox(opt, key=f"ck_{opt}"):
                    selected_options.append(opt)

    # 내부 파이프라인 기본값
    aggregate_lines = True
    line_y_tol = 2.5
    dedupe = "by_location"

    st.markdown("<div class='btn-stack'>", unsafe_allow_html=True)
    submitted = st.button(
        "파일 처리 시작",
        use_container_width=True,
        disabled=(uploaded_file is None or not selected_options),
    )
    st.download_button(
        label="파일 다운로드",
        data=ss.get("processed_bytes", b""),
        file_name=ss.get("processed_filename", "masked_result"),
        use_container_width=True,
        disabled=(not ss.get("processed_bytes")),
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 📚 가이드")
    with st.container(border=True):
        st.write(
            "- 사이드바에서 파일을 업로드하세요.\n"
            "- 보호가 필요한 개인정보 항목을 선택한 뒤 ‘파일 처리 시작’ 버튼을 눌러주세요.\n"
            "- 마스킹이 끝나면 챗봇에게 통계 분석이나 인사이트 관한 질문을 바로 해보실 수 있습니다."
        )
    
    st.markdown("## 🧹 세션 초기화")
    if st.button("초기화", use_container_width=True):    
        for k in list(ss.keys()):
                del ss[k]
        st.rerun()
    st.markdown("### ⚙️ 설정")
    show_file_meta = st.toggle("파일 메타 정보 표시", value=True)
    st.caption(f"세션 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ------------------------
# 처리 핸들러
# ------------------------
if submitted:
    try:
        if uploaded_file and ss.last_file_name != uploaded_file.name:
            ss.messages = []
        ss.process_steps = []
        ss.process_complete = False
        ss.processed_bytes = b""
        ss.processed_filename = ""
        ss.out_masked_csv = ""
        ss.out_converted_csv = ""
        ss.llm_ready = False
        ss.last_llm_result = None
        ss.last_chart_payload = None
        ss.masked_type_counts = {}
        ss.masked_records = []
        ss.enabled_types = set()

        pb = st.progress(0)

        def tick(msg: str, idx: int, total: int):
            ss.process_steps.append(f"• {msg} 완료")
            pb.progress(int(idx / total * 100))

        # 0) 임시 작업 디렉터리 및 원본 저장
        workdir = Path(tempfile.mkdtemp(prefix="pii_ui_"))
        ss.workdir = str(workdir)
        src_path = workdir / uploaded_file.name
        with open(src_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        ss.last_file_name = uploaded_file.name

        total_steps = 5  # 분석, 탐지, 마스킹/치환, 결과물 생성, 변환

        # 1) Intermediate/PII 생성
        tick("텍스트/테이블 분석", 1, total_steps)
        results = agent.run_agent_on_paths(
            [src_path],
            out_dir=workdir,
            pdf_mode="both",
            aggregate_lines=aggregate_lines,
            line_y_tol=float(line_y_tol),
            dedupe=dedupe,
            debug_drops=False,
            stop_on_error=False,
        )
        if not results or ("error" in results[0]):
            raise RuntimeError(results[0].get("error", "PII 처리 실패"))

        pii_csv = Path(results[0]["pii_csv"])
        if not pii_csv.exists():
            raise FileNotFoundError(f"PII CSV가 없습니다: {pii_csv}")

        tick("패턴 탐지", 2, total_steps)
        df_pii = pd.read_csv(pii_csv, dtype=str, keep_default_na=False)
        pii_rows = df_pii.to_dict(orient="records")

        # 2) 마스킹(선택 타입만)
        enabled = {KOR2TYPE[o] for o in selected_options if o in KOR2TYPE}
        if not enabled:
            raise ValueError("선택된 마스킹 타입이 없습니다.")
        masked_records = mask_process(pii_rows, enabled, output_mode="replace")

        # 세션 보관(후속 시각화용)
        ss.enabled_types = enabled
        ss.masked_records = masked_records

        # 3) 적용/산출
        tick("치환 적용", 3, total_steps)

        # 타입별 건수(즉시 통계)
        counts_by_type = {
            t: sum(1 for r in masked_records if (r.get("pii_type") or "").lower() == t)
            for t in enabled
        }
        ss.masked_type_counts = counts_by_type

        # 공통: masked_replace CSV 저장(추후 convert 입력으로 사용)
        out_masked_csv = Path(ss.workdir) / f"{src_path.stem}.masked_replace.csv"
        pd.DataFrame(masked_records).to_csv(out_masked_csv, index=False, encoding="utf-8-sig")
        ss.out_masked_csv = str(out_masked_csv)

        if src_path.suffix.lower() == ".xlsx":
            # 엑셀에 직접 적용
            out_xlsx = Path(ss.workdir) / f"{src_path.stem}_masked.xlsx"
            _total, _applied, _skipped = apply_masks_to_workbook(
                xlsx_path=src_path,
                pii_rows=masked_records,
                out_path=out_xlsx,
                force=False,
                verify=None,
                dry_run=False,
            )
            ss.processed_bytes = out_xlsx.read_bytes()
            ss.processed_filename = out_xlsx.name
        else:
            # (업로드는 xlsx로 제한되어 있으나 호환 유지)
            out_jsonl = Path(ss.workdir) / f"{src_path.stem}.masked_replace.jsonl"
            with open(out_jsonl, "w", encoding="utf-8") as f:
                for r in masked_records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            ss.processed_bytes = out_masked_csv.read_bytes()
            ss.processed_filename = out_masked_csv.name

        # 4) 변환
        tick("LLM용 포맷 변환", 4, total_steps)
        converted_csv = Path(ss.workdir) / f"{src_path.stem}_converted.csv"
        convert_csv_format(ss.out_masked_csv, str(converted_csv))
        ss.out_converted_csv = str(converted_csv)

        # 5) 완료
        tick("파일 생성", 5, total_steps)
        ss.process_complete = True
        ss.masking_done = True
        ss.llm_ready = True
        st.toast("마스킹 및 변환이 완료되었습니다. LLM 분석을 진행할 수 있습니다.", icon="✅")
        st.rerun()

    except Exception as e:
        st.error(f"처리 실패: {e}")

# ------------------------
# 처리 상태 표시
# ------------------------
if ss.get("process_steps"):
    with st.expander("처리 상태 보기", expanded=False):
        for line in ss.process_steps:
            st.write(line)
        if ss.process_complete:
            st.success("처리 완료")

# ------------------------
# 📊 마스킹 상세 분포(선택 항목만, 즉시 통계 포함)
# ------------------------
st.markdown("## 📊 안전한 개인정보 분포 분석")

masked_records = ss.get("masked_records") or []
enabled_types  = set(ss.get("enabled_types") or [])

if masked_records and enabled_types:
    try:
        # 1) 선택한 타입만 필터링
        filtered = [r for r in masked_records
                    if (r.get("pii_type") or "").lower() in enabled_types]

        # 2) 상단 요약 막대(건수)
        counts_by_type = {}
        for r in filtered:
            t = (r.get("pii_type") or "").lower()
            counts_by_type[t] = counts_by_type.get(t, 0) + 1
        title, fig = create_quick_masking_fig(counts_by_type)
        data_uri = fig_to_data_uri(fig)

        st.subheader(title)
        st.markdown(
            f"""
            <div style="margin:0 auto; max-width:80%; max-height:auto">
                <img src="{data_uri}" alt="{title}" style="width:100%; height:auto;"/>
            </div>
            """,
            unsafe_allow_html=True
        )

        # 3) 상세 분포(요구 사양 반영: 성씨/앞자리/도메인/년·월·성별/지역/BIN 등)
        figs = create_pii_breakdown_figs(filtered, top_n=20)
        if figs:
            st.markdown("""
                    <style>
                        .hscroll-wrap{
                            display: flex; flex-direction : row; gap : 16px; overflow-x: auto; padding: 6px 2px 12px 2px; scroll-snap-type : x proximity;
                        }
                        .hscroll-card {
                            flex : 0 0 auto; border-bottom : 1px solid #d4d4d4; background: white; padding : 9px 12px; scroll-snap-align: start; 
                            margin-top:10px; display:flex; flex-direction:column; align-items:center; justify-content: center;
                        }
                        .hscroll-ttl {
                            font-weight:700; margin:2px 0 8px;
                        }
                        .hscroll-img {
                            display:block; max-width:80%; justify-content:center; margin : 0 auto; max-height:auto;
                        }
                        """, unsafe_allow_html = True)
            # 컨테이너 시작
            st.markdown('<div class="hscroll-wrap">', unsafe_allow_html=True)
            # 각 차트(img) 렌더
            for ttl, f in figs:
                data_uri = fig_to_data_uri(f)
                st.markdown(
                    f'<div class="hscroll-card">'
                    f'  <div class="hscroll-ttl">{ttl}</div>'
                    f'  <img class="hscroll-img" src="{data_uri}" alt="{ttl}"/>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            # 컨테이너 끝
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("표시할 차트가 없습니다.")
    except Exception as e:
        st.warning(f"차트 렌더링 실패: {e}")
else:
    st.info("마스킹 처리가 완료된 후 시각화 자료가 표시됩니다.")

# ------------------------
# LLM 쿼리 영역
# ------------------------
st.markdown("## 🔍 Gemini와 함께 다양한 인사이트를 얻어보세요!")

# ------------------------
# 대화/보조 UI — 렌더는 여기 '한 곳'에서만 수행
# ------------------------
if ss.messages:
        for message in ss.messages[-8:]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

# LLM 차트 공통 렌더(세션 기반)
payload = ss.get("last_chart_payload")
if payload and payload.get("chart_data"):
    st.markdown("#### 📈 LLM 요청 차트")
    try:
        fig = render_chart(payload["chart_data"], payload.get("chart_spec") or {})
        if fig:
            st.pyplot(fig)
        else:
            st.info("차트 데이터 포맷을 해석할 수 없습니다.")
    except Exception as e:
        st.warning(f"차트 렌더 실패: {e}")

if run_llm_analysis:
    user_query = st.text_input("", placeholder="Gemini에게 물어보기")
    run_clicked = st.button("분석 실행", use_container_width=True, disabled=not (ss.llm_ready and bool(user_query)))

    if run_clicked:
        try:
            if not ss.out_converted_csv:
                st.error("변환된 CSV를 찾을 수 없습니다. 상단에서 파일 처리부터 진행하세요.")
            else:
                api_key = os.getenv("GEMINI_API_KEY", API_KEY_FALLBACK).strip()
                if not api_key or api_key == "AIzaSyCE9Notum3eif_ljWQMgNI_jtqlM1OfEjI":
                    st.warning("GEMINI_API_KEY가 비어 있습니다. 환경변수 설정을 권장합니다.")

                with st.spinner("LLM 분석 중..."):
                    result = run_llm_analysis(ss.out_converted_csv, user_query, api_key)

                ss.messages.append({"role": "user", "content": user_query})

                if isinstance(result, dict):
                    analysis_text = result.get("analysis_text") or result.get("text") or str(result)
                    ss.messages.append({"role": "assistant", "content": analysis_text})

                    ss.last_chart_payload = {
                        "chart_data": result.get("chart_data"),
                        "chart_spec": result.get("chart_spec") or {},
                    }
                    ss.last_llm_result = result
                else:
                    ss.messages.append({"role": "assistant", "content": str(result)})
                    ss.last_chart_payload = None
                    ss.last_llm_result = None

                st.rerun()

        except Exception as e:
            st.error(f"LLM 분석 실패: {e}")
else:
    st.info("main.py에 run_llm_analysis(file_path, user_query, api_key)를 내보내세요.")
