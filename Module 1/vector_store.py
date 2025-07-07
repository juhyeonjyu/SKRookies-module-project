# 파일 업로드 함수 정의
def create_file(file_path, client):      
    # 파일을 바이너리 읽기 모드로 열기
    with open(file_path, "rb") as file_content:
        result = client.files.create(file=file_content, purpose="assistants")   # 파일 업로드 및 목적을 "assistants"로 지정
    
    return result.id    # 파일의 고유 ID를 반환

# 벡터 스토어 생성 및 파일 연결 함수 정의
def vector_store_with_file(file_path, store_name, client):
    
    vector_store = client.vector_stores.create(name=store_name) # 벡터 스토어 생성
    file_id = create_file(file_path, client)                    # 파일 업로드, 해당 파일의 ID를 불러오기

    # 벡터 스토어의 고유 ID 지정 및 파일 ID 지정
    client.vector_stores.files.create(                          
        vector_store_id=vector_store.id,
        file_id=file_id
    )

    # 벡터 스토어 ID 반환(외부에서 활용 가능하게 함)
    return vector_store.id