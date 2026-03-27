# 챗봇 RAG MCP 서버 설계

## 프로젝트 구조

```
SAMKWANG AI/
├── backend/                    # FastAPI 백엔드
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI 애플리케이션 진입점
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py        # 챗봇 API 엔드포인트
│   │   │   └── documents.py   # 문서 관리 API
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── openai_service.py    # OpenAI API 연동
│   │   │   ├── rag_service.py       # RAG 검색 서비스
│   │   │   └── vector_store.py      # 벡터 DB 관리
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py     # Pydantic 모델
│   │   └── config.py          # 설정 관리
│   ├── requirements.txt
│   └── .env.example
│
├── mcp_server/                 # MCP 서버
│   ├── __init__.py
│   ├── main.py                # MCP 서버 진입점
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── database_tool.py   # DB 생성/관리 도구
│   │   └── query_tool.py      # 쿼리 실행 도구
│   ├── database/
│   │   ├── __init__.py
│   │   └── db_manager.py      # 데이터베이스 관리자
│   └── requirements.txt
│
├── frontend/                   # 웹 프론트엔드
│   ├── index.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── app.js
│   └── package.json (선택사항)
│
├── data/                       # 데이터 저장소
│   ├── documents/              # 업로드된 문서
│   ├── vector_db/              # 벡터 DB 저장소
│   └── database/               # PostgreSQL 관련 스키마/마이그레이션
│
├── tests/                      # 테스트
│   ├── test_backend.py
│   └── test_mcp_server.py
│
├── .env                        # 환경 변수 (gitignore)
├── .gitignore
└── README.md
```

## 기술 스택

### 백엔드
- **FastAPI**: REST API 서버
- **OpenAI**: GPT API 연동
- **LangChain**: RAG 파이프라인 구축
- **Chroma/FAISS**: 벡터 데이터베이스 (로컬)
- **PostgreSQL**: 구조화된 데이터 저장
- **Pydantic**: 데이터 검증
- **python-dotenv**: 환경 변수 관리

### MCP 서버
- **MCP SDK**: Model Context Protocol 서버 구현
- **SQLAlchemy**: ORM (데이터베이스 추상화)
- **PostgreSQL**: 기본 데이터베이스

### 프론트엔드
- **Vanilla JS** 또는 **React**: 간단한 채팅 UI
- **Fetch API**: 백엔드와 통신

## 핵심 기능

### 1. 백엔드 (FastAPI)
- **채팅 API** (`/api/chat`): 사용자 메시지 수신, RAG 검색, OpenAI 호출, 응답 반환
- **문서 업로드 API** (`/api/documents`): 문서 업로드 및 벡터화
- **RAG 파이프라인**: 문서 임베딩 → 벡터 DB 저장 → 유사도 검색 → 컨텍스트 생성

### 2. MCP 서버
- **데이터베이스 생성 도구**: 스키마 정의 및 테이블 생성
- **데이터 삽입 도구**: 구조화된 데이터 입력
- **쿼리 실행 도구**: SQL 쿼리 실행 및 결과 반환
- **MCP 프로토콜**: 챗봇과 통신하여 DB 작업 수행

### 3. RAG 시스템
- **문서 임베딩**: OpenAI embeddings API 사용
- **벡터 검색**: 사용자 질문과 유사한 문서 검색
- **컨텍스트 구성**: 검색된 문서를 프롬프트에 포함

### 4. 프론트엔드
- **채팅 인터페이스**: 메시지 입력 및 표시
- **문서 업로드**: 파일 업로드 기능
- **실시간 응답**: 스트리밍 또는 일반 응답

## 데이터 흐름

1. **문서 업로드**: 사용자 → 프론트엔드 → 백엔드 → 벡터화 → 벡터 DB 저장
2. **데이터 입력**: 사용자 → MCP 서버 → PostgreSQL 저장
3. **채팅 질문**: 사용자 → 프론트엔드 → 백엔드 → RAG 검색 → MCP 서버 쿼리 → OpenAI → 응답

## 환경 변수

```env
OPENAI_API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/chatbot
VECTOR_DB_PATH=./data/vector_db
MCP_SERVER_PORT=8001
BACKEND_PORT=8000
```

## 구현 단계

### 1. 프로젝트 디렉토리 구조 생성 및 기본 설정 파일 작성
- `.gitignore`, `README.md`, `requirements.txt` 생성
- 각 모듈별 디렉토리 구조 생성

### 2. 백엔드 기본 구조 구현
- FastAPI 앱 초기화
- 설정 관리 (`config.py`)
- 환경 변수 로드 (`.env`)

### 3. OpenAI 서비스 연동
- OpenAI API 클라이언트 설정
- 임베딩 생성 함수
- 채팅 완성 API 호출

### 4. 벡터 DB 및 RAG 서비스 구현
- Chroma 또는 FAISS 벡터 DB 설정
- 문서 임베딩 및 저장
- 유사도 검색 기능
- RAG 컨텍스트 생성

### 5. MCP 서버 구현
- MCP 서버 기본 구조
- 데이터베이스 생성/관리 도구
- 쿼리 실행 도구
- MCP 프로토콜 통신

### 6. 백엔드 API 엔드포인트 구현
- `/api/chat` - 채팅 엔드포인트 (RAG + OpenAI)
- `/api/documents` - 문서 업로드 엔드포인트
- MCP 서버와의 통신 연동

### 7. 프론트엔드 UI 구현
- 채팅 인터페이스 (HTML/CSS/JS)
- 메시지 입력 및 표시
- 문서 업로드 UI
- API 통신 (Fetch API)

### 8. 통합 테스트 및 문서화
- 단위 테스트 작성
- 통합 테스트
- API 문서화
- 사용 가이드 작성

