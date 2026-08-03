# emotion healer

감정과 생각을 정리되지 않은 채로 적으면, 그걸 정리해서 돌려주고 지금 필요한 게
공감인지 방법인지 판단해서 답하는 대화 서비스.

지금은 뼈대만 있는 상태다. LangGraph 노드 하나가 LLM을 한 번 호출하고, 그 답을
브라우저로 흘려보낸다.

## 실행

Codex CLI 로그인이 인증을 대신하므로 API 키는 필요 없다.

```bash
npm install -g @openai/codex
codex login

uv sync
uv run uvicorn app.main:app --reload
```

http://127.0.0.1:8000 접속.

## 구조

```
app/
  main.py          FastAPI. GET / 와 POST /api/chat(SSE) 두 개
  graph.py         LangGraph. 노드 하나짜리 그래프
  prompt.py        시스템 프롬프트. 사실상 이 서비스의 본체
  llm/provider.py  벤더 이름이 등장하는 유일한 파일
static/index.html  채팅 UI. 빌드 도구 없음
tests/             그래프 배선 스모크 테스트
```

## 모델 교체

`app/llm/provider.py`가 `BaseChatModel`을 돌려주고, 나머지 코드는 그 타입만 안다.
`graph.py`는 `algocean_codex_oauth`를 import하지 않는다. 다른 모델로 갈아타려면
`provider.py` 본문만 바꾸면 되고 호출부는 건드릴 게 없다.

로컬은 Codex OAuth, 배포는 API 키를 쓴다. 코드 수정 없이 환경변수로 전환된다.

```bash
export ALGOCEANCODEXOAUTH_AUTH=api_key
export ALGOCEANCODEXOAUTH_API=sk-...
```

## 알려진 제약

**배포 시 사용자별 API 키를 못 받는다.** `algocean-codex-oauth` 0.2.6은 키를
`ALGOCEANCODEXOAUTH_API` 환경변수에서만 읽는다(`auth_mode.load_api_key_from_env`).
프로세스 단위라 요청마다 다른 사용자 키를 넣을 수 없다. 셋 중 하나가 필요하다.

- 라이브러리에 `api_key` 생성자 인자 추가 (가장 깔끔, 라이브러리가 우리 것이니 가능)
- `provider.py`에서 api_key 모드일 때만 `ChatOpenAI`를 직접 생성 (어차피 라이브러리도
  내부적으로 `ChatOpenAI`에 위임한다)
- 사용자당 프로세스 분리 (비추천)

**OAuth 모드의 스트리밍은 토큰 단위가 아니다.** Codex CLI를 서브프로세스로
호출하는 구조라 응답이 큰 덩어리로 온다. 측정해보니 짧은 답은 한 덩어리, 긴 답도
두세 덩어리 수준이었다. 타이핑되듯 흐르는 느낌을 원하면 api_key 모드를 쓰거나
클라이언트에서 덩어리를 쪼개 뿌려야 한다.

## 앞으로

### 대화 기록 저장

지금은 `MemorySaver`라 프로세스가 죽으면 대화가 사라진다. LangGraph의
checkpointer는 `MemorySaver` / `SqliteSaver` / `PostgresSaver`가 전부 같은
`BaseCheckpointSaver` 인터페이스여서, 교체는 `graph.py`의 한 줄이다.

SQLite로 시작해서 나중에 PostgreSQL로 옮기는 건 코드 관점에서 부담이 없다. 진짜
비용은 코드가 아니라 데이터 이관이다. 그래서 뼈대 단계에서 Docker에 Postgres를
미리 띄울 이유가 없다. 실사용 데이터가 쌓이기 시작하고 여러 기기에서 붙게 되는
시점이 옮길 때다.

### RAG를 확장 DB로

이게 이 서비스에서 하고 싶은 방향이다. 일반적인 RAG처럼 고정된 문서를 검색하는
게 아니라, 사용자에 대해 계속 갱신되는 저장소로 쓴다. 자주 언급하는 사람, 반복해서
힘들어하는 상황, 지난번에 실제로 도움이 됐던 접근 같은 것들. 스키마를 미리 정할 수
없고 계속 변하는 종류의 데이터라, 관계형 테이블보다 이쪽이 맞다.

이게 자리를 잡으면 관계형 DB가 맡을 몫은 오히려 줄어든다. 계정, 세션처럼 구조가
확실한 것만 남는다.

임베딩 모델은 별도로 정한다. `algocean-codex-oauth`는 채팅 전용이라 임베딩을
지원하지 않는다(패키지 전체에 `embed` 문자열이 없다). 로컬 모델을 쓰면 API 키 없이
돌아가고 감정 기록이 외부로 나가지 않는다는 장점이 있다.

그래프는 이렇게 늘어난다.

```
지금:  START → respond → END
이후:  START → retrieve → respond → extract → END
                (기억 조회)          (기억 추출·저장)
```

`extract`는 응답 스트리밍이 끝난 뒤 도는 노드라 사용자가 기다리지 않는다.

## 위기 대응

자해나 자살을 암시하는 표현에는 평소 응답 방식을 멈추고 24시간 상담 창구를
안내하도록 프롬프트에 넣어두었다. 자살예방상담전화 109, 정신건강위기상담전화
1577-0199.

이 서비스는 상담을 대체하지 않는다.
