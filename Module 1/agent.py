import json, openai, os
from dotenv import load_dotenv
from module import check_black_list
from vector_store import vector_store_with_file

# .env 파일에서 환경 변수 불러오기 (예: API 키)
load_dotenv()

OPEN_API_KEY = os.getenv("OPEN_API_KEY")        # 환경 변수에서 OPEN_API_KEY 값을 불러와 변수에 저장
client = openai.OpenAI(api_key=OPEN_API_KEY)    # OpenAI 클라이언트를 생성 및 API 키 인증

# 하위 에이전트 함수 정의
# 악성 URL 판단 결과에 기반한 OpenAI 응답 생성 
def agent_call(url):
    client = openai.OpenAI(api_key=OPEN_API_KEY)
    store_id = vector_store_with_file(
        "./악성url관련자료.pdf",
        "knowledge_base",
        client
    )

    if url:
        result = check_black_list(url)                  # 사용자 정의 함수(URL이 블랙리스트에 있는지 검사)
        client = openai.OpenAI(api_key=OPEN_API_KEY)    # OpeinAI API클라이언트 생성

        # 에이전트 역할 (system role), 사용자 입력 정의
        input = [{
            "role" : "system",
            "content" : "당신은 악성 URL 결과를 잘 리포팅해서 상위 에이전트에게 전달하는 한국어 에이전트입니다.\
                당신은 블랙리스트에 존재한다는 문자나 0 또는 1을 받습니다. 블랙리스트에 존재하면 악성 URL입니다.\
                0이면 정상 URL, 1이면 악성 URL을 뜻하고 이는 ML모델에 넣은 결과입니다. 정상 URL은 그냥 상위 에이전트에게 정상이라고 전달하면 되고\
                악성 URL이면 벡터 스토어의 파일에는 악성 URL에 대한 자료가 있는데 이걸로 해당 URL에 대한 정보를 가져오는게 아니라\
                왜 악성 URL인지에 대한 분석을 하는데 용이한 자료입니다. 해당 자료를 통해 악성 URL이면 분석결과까지 리포팅해서\
                최대한 주 내용만 다 담아서 간단하게 답변을 구성해주세요."
        },
        {
            "role" : "user",
            "content" : f"사용자 URL: {url} 결과 : {str(result)}"      # 사용자에게 받은 URL과 검사 결과 전달
        }]

        # OpenAI API 호출 
        response = client.responses.create(
            model="gpt-4o",
            input = input,
            tools=[{"type" : "file_search",
                    "vector_store_ids" : [store_id]}]      # 생성된 벡터 스토어 ID 연결
        )
        return response.output_text     # OpenAI 응답 텍스트 반환

# 상위 에이전트 클래스 정의(사용자 요청을 받아 function call로 하위 에이전트 호출 및 응답)
class Agent:
    def __init__(self, client):
        self.client = client    # OpenAI API 클라이언트 저장

        # function(하위 에이전트) 호출, web_search
        self.tools = [{
            "type": "function",
            "name": "agent_call",
            "description": "사용자로부터 악성 URL 관련 판단 질문을 받으면 URL 검사와 리포팅을 위해 하위 에이전트를 호출하는 함수입니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        },
        {
            "type": "web_search_preview"
        }
        ]

        # context를 관리할 변수
        self.messages = []

        # 에이전트 역할 (system role)
        self.messages.append(
            {"role" : "system",
            "content" : "당신은 한국어 상담 에이전트입니다. 사용자로부터의 질문을 툴을 사용하게 적절하게 대답해주세요.\
                악성 URL에 관한 질문이 들어올 때만 다음과 같이 대답하면 됩니다.:\n\
                악성 URL에 대한 질문이 들어오면 Function call을 이용해 사용자의 입력으로부터 URL을 건내주어 응답을 받아야 합니다.\
                Function call에선 하위 에이전트가 URL을 분석해서 당신에게 리포팅을 해줄 것이며 당신은 그 결과를 받고\
                정상이면 그냥 답변하면 되고, 블랙리스트에 존재하면 블랙리스트에 관해서 얘기해주고 블랙리스트에 존재하는 악성 url이라고 하면됩니다.\
                블랙리스트에 없는데 모델이 악성 url이라 판단하면 해당 사실을 알려주세요. 모델 결과 악성 url로 판단되면 하위 에이전트의 리포트를 참조하여 사용자에게 알려주세요.\
                그리고 Websearch 툴을 사용하여 대안 사이트 3~4개를 추천해주세요. 이때 사용자에게 목적을 물어보고\
                목적이 확인되면 일반적이고 대중적인 사이트를 추천해주세요."
            }
        )

    # OpenAI가 요청한 function call 실행, 결과를 messages에 저장하는 메서드
    def function_call(self, calls):
        result = []

        # 호출된 function 요청을 차례대로 처리
        for call in calls:
            if call.type != "function_call":    # type가 function_call이 아니면 무시
                continue   

            try :
                result.append(call)                         # 호출 요청도 메시지에 포함
                function_args = json.loads(call.arguments)  # OpenAI가 전달한 arguments를 JOSN으로 파싱
                output = agent_call(**function_args)        # agent_call 함수 호출       

                # 호출 결과를 function_call_output 형태로 메시지에 추가
                result.append({
                    "call_id": call.call_id,            # 어떤 호출의 응답인지 식별
                    "type": "function_call_output",     # 응답 타입 
                    "output": str(output)               # 함수 실행 결과 텍스트
                })

            # 예외 처리
            except Exception as e:

                # 오류 발생 시 오류 메시지를 function_call_output으로 리턴
                result.append({
                    "call_id": call.call_id,            
                    "type": "function_call_output",
                    "output": str(e)
                })
        self.messages.extend(result)    # 처리 결과를 전체 메시지를 기록에 추가

    def chat(self, query) : 
        # context 추가
        self.messages.append({
            "role": "user",
            "content": query
        })

        # 모델에 응답 요청
        response = self.client.responses.create(
            model="gpt-4o",
            input=self.messages,
            tools=self.tools,
            tool_choice="auto"
        )

        # function_call이 없는 경우, 바로 응답 반환
        if not response or not response.output or all(c.type != "function_call" for c in response.output):
            self.messages.append(
                {"role" : "assistant",
                "content" : response.output_text}
            )
            return response.output_text
        
        # function_call이 있는 경우 처리
        self.function_call(response.output)

        # function_call 결과 포함해서 최종 응답 생성
        final_response = self.client.responses.create(
            model="gpt-4o",
            input=self.messages
        )

        # context 추가
        self.messages.append(
            {"role" : "assistant",
             "content" : final_response.output_text}
        )

        # 최종 응답 텍스트
        return final_response.output_text

if __name__ == "__main__":
    client = openai.OpenAI(api_key=OPEN_API_KEY)
    agent = Agent(client)
    agent.chat("https://0586.yahwagsc.pro 이거 어때?")
