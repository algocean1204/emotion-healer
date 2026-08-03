# emotion healer

감정과 생각을 정리되지 않은 채로 적으면, 그걸 정리해서 돌려주고 지금 필요한 게
공감인지 방법인지 판단해서 답하는 대화 서비스.

## 기술

- **LangGraph** — 메인 그래프가 공감이냐 방법이냐를 먼저 판단하고, 서브그래프
  두 개가 각각 응답한다.
- **FastAPI** — SSE로 토큰을 흘려보낸다. 페이지 하나에 엔드포인트 셋.
- **AlgoceanCodexOAuth** — LangChain `BaseChatModel` 구현체. 로컬 Codex OAuth
  구독으로 GPT를 쓰고, 모델과 추론 강도는 화면에서 바꾼다.
- **단일 HTML** — 빌드 도구 없이 `static/index.html` 하나.

## 실행

```bash
codex login
uv sync
uv run healer run
```
