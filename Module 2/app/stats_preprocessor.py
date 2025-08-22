import pandas as pd
import re

def preprocess_stats(df: pd.DataFrame) -> dict:
    stats = {}

    # 1) 이메일 → 도메인 (기존 코드)
    if "email" in df.columns:
        df["email_clean"] = df["email"].str.replace(r"[*xX]+", "", regex=True)
        df["email_domain"] = df["email_clean"].str.split("@").str[-1]
        stats["email_domain_top10"] = df["email_domain"].value_counts().head(10).to_dict()

    # 2) 전화번호 → 뒷 4자리 통계 (수정된 부분)
    if "phone" in df.columns:
        # 전화번호에서 숫자만 추출
        df["phone_clean"] = df["phone"].str.replace(r"[^0-9]", "", regex=True)
        # 문자열의 마지막 4자리를 추출하여 새로운 컬럼 생성
        df["phone_last_4"] = df["phone_clean"].str[-4:]

        # 뒷 4자리 빈도 통계를 딕셔너리에 저장
        stats["phone_last_4_counts"] = df["phone_last_4"].value_counts().to_dict()

    # 3) 주민등록번호(rrn) → 생년월일, 성별 (수정된 부분)
    if "rrn" in df.columns:
        # RRN을 파싱하여 생년과 성별을 반환하는 헬퍼 함수
        def parse_rrn_for_stats(rrn_str):
            rrn_clean = re.sub(r'[^0-9]', '', str(rrn_str))
            
            # 최소 7자리 이상인 경우만 처리
            if len(rrn_clean) >= 7:
                birth_year_yy = int(rrn_clean[0:2])
                gender_code = int(rrn_clean[6])
                
                # 성별과 세기 결정
                if gender_code in [1, 3]:
                    gender = '남자'
                    century = 1900
                elif gender_code in [2, 4]:
                    gender = '여자'
                    century = 1900
                else:
                    return None, None
                
                full_birth_year = century + birth_year_yy
                return full_birth_year, gender
            else:
                return None, None

        # apply 메서드를 사용하여 새로운 컬럼을 생성합니다.
        parsed_rrn = df["rrn"].apply(
            lambda x: pd.Series(parse_rrn_for_stats(x), index=['full_birth_year', 'gender'])
        )
        
        # 생성된 컬럼을 DataFrame에 추가
        df = pd.concat([df, parsed_rrn], axis=1)

        # 새로운 통계 집계
        if 'gender' in df.columns and not df['gender'].isnull().all():
            stats["rrn_gender_counts"] = df['gender'].value_counts().to_dict()
        else:
            stats["rrn_gender_counts"] = {}

        if 'full_birth_year' in df.columns and not df['full_birth_year'].isnull().all():
            stats["rrn_full_birth_year_counts"] = df['full_birth_year'].value_counts().sort_index().to_dict()
        else:
            stats["rrn_full_birth_year_counts"] = {}
        
    # 4) 운전면허 (기존 코드)
    if "driver_license" in df.columns:
        df["dl_clean"] = df["driver_license"].str.replace(r"[^0-9A-Za-z]", "", regex=True)
        df["dl_prefix"] = df["dl_clean"].str[:2]
        stats["dl_prefix_counts"] = df["dl_prefix"].value_counts().to_dict()

    # 5) 이름 → 성씨 (기존 코드)
    if "name" in df.columns:
        df["name_clean"] = df["name"].str.replace(r"[*xX]", "", regex=True)
        df["family_name"] = df["name_clean"].str[0]
        stats["family_name_top10"] = df["family_name"].value_counts().head(10).to_dict()

    # 6) 주소 → 시/도 레벨 (기존 코드)
    if "address" in df.columns:
        df["address_clean"] = df["address"].str.replace(r"[*xX]", "", regex=True)
        df["address_region"] = df["address_clean"].str.split().str[0]
        stats["address_region_top10"] = df["address_region"].value_counts().head(10).to_dict()

    return stats



def prepare_prompt_from_stats(stats: dict, user_query: str) -> str:
    return f"""
    너는 데이터 분석가다.

    아래는 개인정보 데이터에서 사전 집계한 통계다:
    {stats}

    사용자의 요청: "{user_query}"

    규칙:
    - 제공된 통계값만 바탕으로 답변해라.
    - 데이터 전체에 대해 집계된 결과라고 가정하라.
    - 불필요한 설명은 줄이고, 통계 수치와 간단한 해설을 제시하라.
    """