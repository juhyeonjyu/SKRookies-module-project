import re, socket, whois, dns.resolver
import pandas as pd
from datetime import datetime
from ipwhois import IPWhois
from urllib.parse import urlparse
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score

def safe_days(d) :
    try :
        if isinstance(d, list) :
            d = d[0]
            return (datetime.utcnow() - d).days
    except :
        return -1
    
# Feature 추출
# 참고 자료 : https://archive.ics.uci.edu/dataset/327/phishing+websites
def extract_url_features(url) :
    feature = {}
    parsed = urlparse(url)
    host = parsed.hostname

    # 기본 URL 기반 Feature
    feature['url_length'] = len(url)            # URL 전체 문자열 길이
    feature['num_dots'] = url.count('.')        # URL 내 점(.)의 개수
    feature['has_ip'] = int(bool(re.search(r'\d+\.\d+\.\d+\.\d+', url)))    # IP 주소 포함 여부
    # feature['has_https'] = int(parsed.scheme == 'https')            # HTTPS 사용 여부      
    feature['num_special_chars'] = len(re.findall(r'[^\w]', url))   # 특수문자 수 (@, ?, =, % 등)
    feature['has_at_symbol'] = int('@' in url)                      # @ 기호 포함 여부
    feature['path_length'] = len(parsed.path)                       # URL 경로 길이
    feature['num_digits'] = len(re.findall(r'\d', url))             # 숫자 개수

    # WHOIS 도메인 생성일
    try :
        w = whois.whois(host)
        feature['domain_created_days'] = safe_days(w.creation_date)
    except :
        feature['domain_created_days'] = -1

    # IP WHOIS: NetName & ASN 설명
    # try:
    #     ip = socket.gethostbyname(host)
    #     ipinfo = IPWhois(ip).lookup_rdap()
    #     net = ipinfo.get("network", {})
    #     feature["netname_words"] = len(re.findall(r"\w+", str(net.get("name", ""))))
    #     feature["asn_words"] = len(re.findall(r"\w+", ipinfo.get("asn_description", "")))
    # except:
    #     feature["netname_words"] = -1
    #     feature["asn_words"] = -1

    # DNS SOA TTL
    try:
        soa = dns.resolver.resolve(host, "SOA")
        feature["soa_default_ttl"] = soa.rrset.ttl
    except:
        feature["soa_default_ttl"] = -1

    return feature

# 특징 병렬 추출
# URL 개수가 많아 멀티코어 CPU 활용
def extract_features_parallel(urls):
    with Pool(cpu_count()) as pool:
        return list(tqdm(pool.imap(extract_url_features, urls), total=len(urls), desc="Extracting Features"))
    
if __name__ == '__main__' :
    # 데이터 불러오기
    normal = pd.read_csv('정상url_10000.csv')
    phishing = pd.read_csv('한국인터넷진흥원_피싱사이트 URL_20231231.csv')

    # 데이터 통합
    df = pd.concat([normal, phishing], ignore_index=True)
    df = df.dropna(subset=['url']).drop_duplicates(subset=['url'])

    # Feature, Target 설정
    features = extract_features_parallel(df['url'])
    X = pd.DataFrame(features)
    y = df['label'].astype(int)

    # 학습 데이터 및 테스트 데이터 분할
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # XGBoost 모델 생성 및 학습
    # Extreme Gradient Boosting : Gradient Boosting 기법 확장 알고리즘 ➡️ 여러 개의 약한 모델을 순차적으로 학습해서 오류를 보완하며 성능을 높이는 방식 ➡️ 정확도와 실행 속도 사이의 균형이 뛰어남
    # 학습 방식 : 각 트리는 이전까지의 예측이 틀린 부분을 "집요하게 물고 늘어져서" 전체 성능을 개선함

    # 피싱 URL 탐지에서 유리한 이유 : 
    # 다양한 URL 특성(길이, 도메인 구조, 키워드 포함 여부 등)은 복잡하고 상호작용 많음 ➡️ XGBoost는 이런 비선형적 관계를 잘 포착하며 특성 간 조합도 자동으로 학습함
    xgb_model = XGBClassifier(
        n_estimators=200,           # 부스팅할 트리 개수 : 많을수록 모델 복잡도와 과적합 가능성 증가
        max_depth=4,                # 각 트리의 최대 깊이 : 깊을수록 더 복잡한 패턴 학습 가능, 그러나 과적합 위험 있음
        learning_rate=0.1,          # 학습률 : 작을수록 학습이 느리지만 안정적임
        random_state = 42,          # 난수 고정
        use_label_encoder=False,    # 라벨 인코더 사용 여부
        eval_metric='logloss',      # 평가 지표 설정 : 로그 손실 함수, 작을수록 예측 확률이 정답에 가까움
        n_jobs=-1                   # 사용할 CPU 쓰레드 수 : -1 : 모든 코어 사용
    )

    xgb_model.fit(X_train, y_train)

    # 예측 및 성능 평가
    y_pred = xgb_model.predict(X_test)
    print("\n정확도:", accuracy_score(y_test, y_pred))
    print(classification_report(y_test, y_pred))