import re, numpy as np
from urllib.parse import urlparse

def extract_url_features(url) :
    feature = {}
    parsed = urlparse(url)

    # 기본 URL 기반 Feature
    feature['url_length'] = int(len(url) > 75)                                      # URL 전체 문자열 길이
    feature['num_dots'] = np.log1p(url.count('.'))                                  # URL 내 점(.)의 개수
    feature['has_ip'] = int(bool(re.search(r'\d+\.\d+\.\d+\.\d+', url)))            # IP 주소 포함 여부  
    feature['num_special_chars'] = int(len(re.findall(r'[^\w]', url)) > 5)          # 특수문자 수 (@, ?, =, % 등)
    feature['has_at_symbol'] = int('@' in url)                                      # @ 기호 포함 여부
    feature['path_length'] = np.log1p(len(parsed.path))                             # URL 경로 길이
    feature['num_digits'] = np.log1p(len(re.findall(r'\d', url)))                   # 숫자 개수

    return feature