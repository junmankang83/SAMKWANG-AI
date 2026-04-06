# SAMKWANG AI

FastAPI 기반 챗봇 백엔드, MCP 서버, 간단한 프론트엔드를 포함하는 RAG 시스템 템플릿입니다.

## RAG 문서 폴더(선택)

채팅 질문에 따라 `document/` 아래에서 **우선 검색**하는 하위 폴더가 나뉩니다. 폴더를 만든 뒤 관리자 **문서 동기화**(`POST /api/documents/sync`)를 실행하면 인덱스에 `rel_path`가 반영됩니다.

- `failure encyclopedia/` — 불량·결함 관련 질문
- `knowledge/` — 일반 지식(위 두 유형에 안 맞을 때 기본)
- `companyrule/` — 규정·내규 문의

폴더명은 루트 `.env`의 `RAG_FAILURE_SUBDIR`, `RAG_KNOWLEDGE_SUBDIR`, `RAG_RULES_SUBDIR`로 바꿀 수 있습니다.

## 구성

- `backend/`: FastAPI 앱, RAG 서비스, OpenAI 연동
- `mcp_server/`: PostgreSQL을 관리하는 MCP 도구
- `frontend/`: 기본 HTML/CSS/JS 채팅 UI
- `data/`: 문서, 벡터 DB, 데이터베이스 파일 저장소

## 설치

### 백엔드

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### MCP 서버

```bash
cd mcp_server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 프론트엔드

간단한 정적 파일이므로 `frontend/index.html`을 로컬 서버(예: `python -m http.server`)로 제공하거나 백엔드에서 서빙하도록 구성할 수 있습니다.

## 환경 변수

`.env` 파일을 루트에 생성하고 다음 값을 채워주세요 (필요 시 수정).

```
OPENAI_API_KEY=sk-***
DEFAULT_CHAT_MODEL=gpt-5.4
DATABASE_URL=postgresql://user:password@localhost:5432/chatbot
VECTOR_DB_PATH=./data/vector_db
MCP_SERVER_PORT=8001
BACKEND_PORT=8000
```

`DEFAULT_CHAT_MODEL` 기본값은 `gpt-5.4`입니다. API에서 거절되면 `gpt-4o`로 변경하거나 UI에서 다른 모델을 선택하세요.

Google 연동 로그인은 루트 [`README.md`](../README.md)의 **Google 연동 로그인** 절차와 `GOOGLE_OAUTH_*` 환경 변수, [`backend/migrations/001_add_google_oauth.sql`](../backend/migrations/001_add_google_oauth.sql)를 참고하세요.

## 실행

1. 백엔드: `uvicorn app.main:app --reload`
2. MCP 서버: `python -m mcp_server.main`
3. 프론트엔드: 정적 파일 제공

## 테스트

```
python -m pytest tests
```

