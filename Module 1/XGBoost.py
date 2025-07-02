import re, joblib, pandas as pd, numpy as np
from urllib.parse import urlparse
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score

# 데이터 정규화
def normalize_url(url):
    url = url.strip()
    url = re.sub(r'^https?://', '', url)  # http:// 또는 https:// 제거
    return url

# Feature 추출
# 참고 자료 : https://archive.ics.uci.edu/dataset/327/phishing+websites
def extract_url_features(url) :
    feature = {}
    url = normalize_url(url)
    try:
        parsed = urlparse(url)
    except ValueError as e:
        print(f"[URL 파싱 오류] {url} → {e}")
        return {}  # 또는 기본값 반환

    # 기본 URL 기반 Feature
    feature['url_length'] = int(len(url) > 75)                                      # URL 전체 문자열 길이
    feature['num_dots'] = np.log1p(url.count('.'))                                  # URL 내 점(.)의 개수
    feature['has_ip'] = int(bool(re.search(r'\d+\.\d+\.\d+\.\d+', url)))            # IP 주소 포함 여부  
    feature['num_special_chars'] = int(len(re.findall(r'[^\w]', url)) > 5)          # 특수문자 수 (@, ?, =, % 등)
    feature['has_at_symbol'] = int('@' in url)                                      # @ 기호 포함 여부
    feature['path_length'] = np.log1p(len(parsed.path))                             # URL 경로 길이
    feature['num_digits'] = np.log1p(len(re.findall(r'\d', url)))                   # 숫자 개수

    return feature
    
if __name__ == '__main__' :
    # 데이터 전처리
    # 데이터 불러오기
    # f = pd.read_csv('url.csv', encoding='latin1')
    # label 1 데이터 추출
    # label_1 = df[df['label'] == 1]
    # label 0 데이터에서 label 1 개수만큼 랜덤 샘플링
    # label_0 = df[df['label'] == 0].sample(n=len(label_1), random_state=42)
    # 합쳐서 섞기
    # balanced = pd.concat([label_1, label_0]).sample(frac=1, random_state=42).reset_index(drop=True)
    # print(balanced_df['label'].value_counts())
    # 데이터 저장 및 새로운 데이터 불러오기
    # balanced.to_csv('data.csv', index=False, encoding='utf-8-sig')
    df = pd.read_csv('data.csv')

    # 순차적 특징 추출
    features = [extract_url_features(str(url)) for url in tqdm(df['url'].fillna(''), desc='Extracting Features')]

    # Feature, Target 설정
    X = pd.DataFrame(features)
    y = df['label'].astype(int)

    # 학습 데이터 및 테스트 데이터 분할
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # XGBoost 모델 생성 및 학습
    # 참고 자료 : 논문 - URL 주요특징을 고려한 악성URL 머신러닝 탐지모델 개발 - 김영준, 이재우
    # Extreme Gradient Boosting : Gradient Boosting 기법 확장 알고리즘  여러 개의 약한 모델을 순차적으로 학습해서 오류를 보완하며 성능을 높이는 방식 ➡️ 정확도와 실행 속도 사이의 균형이 뛰어남
    # 학습 방식 : 각 트리는 이전까지의 예측이 틀린 부분을 "집요하게 물고 늘어져서" 전체 성능을 개선함

    # 피싱 URL 탐지에서 유리한 이유 : 
    # 다양한 URL 특성(길이, 도메인 구조, 키워드 포함 여부 등)은 복잡하고 상호작용 많음  XGBoost는 이런 비선형적 관계를 잘 포착하며 특성 간 조합도 자동으로 학습함
    xgb_model = XGBClassifier(
        n_estimators=200,           # 부스팅할 트리 개수 : 많을수록 모델 복잡도와 과적합 가능성 증가
        max_depth=4,                # 각 트리의 최대 깊이 : 깊을수록 더 복잡한 패턴 학습 가능, 그러나 과적합 위험 있음
        learning_rate=0.5,          # 학습률 : 작을수록 학습이 느리지만 안정적임
        random_state = 42,          # 난수 고정
        use_label_encoder=False,    # 라벨 인코더 사용 여부
        eval_metric='logloss',      # 평가 지표 설정 : 로그 손실 함수, 작을수록 예측 확률이 정답에 가까움
        n_jobs=-1,                  # 사용할 CPU 쓰레드 수 : -1 : 모든 코어 사용
    )

    xgb_model.fit(X_train, y_train)

    # 예측 및 성능 평가
    y_pred = xgb_model.predict(X_test)
    print("\n정확도:", accuracy_score(y_test, y_pred))
    print(classification_report(y_test, y_pred))

    # 피처 중요도 출력
    importances = xgb_model.feature_importances_
    feature_names = X.columns

    # 보기 좋게 출력
    for name, score in zip(feature_names, importances):
        print(f"{name:20s} : {score:.4f}")

    # 모델 저장
    joblib.dump(xgb_model, 'XGBoost_model.pkl')

