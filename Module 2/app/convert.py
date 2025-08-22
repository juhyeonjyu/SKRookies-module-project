# convert for llm
import pandas as pd

def convert_csv_format(input_path: str, output_path: str) -> None:
    """
    CSV 파일의 header 값을 영문 표준 컬럼으로 매핑하고,
    동일 row 기준으로 pivot 후 변환된 CSV를 저장한다.
    """
    df = pd.read_csv(input_path)

    # header 값 확인 (디버깅용)
    print("header unique values:", df["header"].unique())

    # header 매핑 정의
    header_mapping = {
        "주소": "address",
        "집주소": "address",
        "운전면허번호": "driver_license",
        "운전면허": "driver_license",
        "Email 주소": "email",
        "이메일": "email",
        "성명": "name",
        "이름": "name",
        "연락처": "phone",
        "전화번호": "phone",
        "주민등록번호": "rrn",
        "주민번호": "rrn"
    }

    # header → 영문 컬럼명 매핑
    df["mapped_header"] = df["header"].map(header_mapping)

    # pivot: 같은 row → 한 사람의 레코드
    df_pivot = df.pivot_table(
        index="row",
        columns="mapped_header",
        values="text",
        aggfunc="first"
    ).reset_index(drop=True)

    # 원하는 컬럼 순서
    ordered_cols = ["address", "driver_license", "email", "name", "phone", "rrn"]

    # 매핑되지 않은 컬럼이 있어도 에러 안 나도록 처리
    existing_cols = [col for col in ordered_cols if col in df_pivot.columns]
    df_converted = df_pivot.reindex(columns=existing_cols)

    # CSV 저장
    df_converted.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"✅ 변환 완료: {output_path}")


# CLI 실행 가능하도록
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CSV 파일 헤더 변환 및 피벗 처리")
    parser.add_argument("input", help="입력 CSV 파일 경로")
    parser.add_argument("output", help="출력 CSV 파일 경로")
    args = parser.parse_args()

    convert_csv_format(args.input, args.output)