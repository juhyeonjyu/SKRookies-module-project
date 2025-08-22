import pandas as pd
import json

def load_data(file_path: str):
    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    elif file_path.endswith(".json"):
        df = pd.read_json(file_path)
    elif file_path.endswith(".jsonl"):
        df = pd.read_json(file_path, lines=True)
    elif file_path.endswith(".xlsx"):   # ✅ 추가 부분
        df = pd.read_excel(file_path)
    else:
        raise ValueError("지원하지 않는 파일 형식입니다. CSV, JSON, JSONL, XLSX만 가능합니다.")
    return df
