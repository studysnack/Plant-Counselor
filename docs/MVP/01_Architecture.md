# 01. 아키텍처

## 1. 전체 그림

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (Next.js 16)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Sidebar    │  │   ChatPanel  │  │  Pages (Home/...)  │  │
│  │  + popover  │  │   (SSE 수신)  │  │                    │  │
│  └─────┬───────┘  └──────┬───────┘  └─────────┬──────────┘  │
│        │ Zustand stores (auth, chat, theme)   │             │
│        └──────────────┬─────────────────────┬─┘             │
│                       ▼                     ▼               │
│                  TanStack Query        fetch wrapper        │
└─────────────────────────┬───────────────────┬───────────────┘
                          │ HTTPS / SSE       │ Bearer (Supabase JWT)
                          ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (uvicorn)                  │
│  Routers ─► Services ─► Repositories ─► supabase-py ─┐      │
│     │                                                │      │
│     └─► /chat/message ─► ChatOrchestrator (ReAct)    │      │
│             │                    │                   │      │
│             ▼                    ▼                   ▼      │
│      LLMClient (Gemini)  SkillRegistry (20 skills)  PostgREST│
└──────────────────┬───────────────────────────────────┬──────┘
                   ▼                                     ▼
          Google Gemini API                  Supabase (PostgreSQL + Auth)
```

## 2. 계층 (백엔드)

각 계층은 한 가지 책임만 갖습니다.

| 계층 | 역할 | 예시 |
|------|------|------|
| **Router** | HTTP I/O + 인증 + Pydantic 검증 | `plants.py`, `chat.py` |
| **Service** | 비즈니스 로직 | `BudService.update_progress()` 가 repo 호출 + 자동 전이 |
| **Repository** | supabase-py PostgREST CRUD 단일 책임 | `BudRepository.create()` 가 `db.table(...).insert()` |
| **Schema** | API 입출력 Pydantic 모델 | `PlantOut`, `BudOut` |

### DB 접근 정책

- 모든 DB 접근은 **supabase-py PostgREST HTTP**로 이루어진다 (SQLAlchemy/psycopg2 미사용).
- 이유: Supabase pooler ENOTFOUND + 직접 연결 IPv6 전용 → psycopg2 연결 불가. PostgREST REST API(HTTPS, service_role_key로 RLS 우회)로 대체.
- supabase-py는 각 요청을 즉시 반영하므로 명시적 `commit()`/`flush()` 트랜잭션 관리가 없다. Repository는 `SimpleNamespace` 행 객체를 반환.
- 행 조회는 `maybe_single()` 대신 `.limit(1) + res.data[0]` 패턴을 사용 (빈 결과 처리).

## 3. 계층 (프론트엔드)

| 계층 | 역할 |
|------|------|
| **app/ (페이지)** | 라우팅, 데이터 페치(useQuery), UI 조립 |
| **components/** | 재사용 컴포넌트 (Sidebar, ChatPanel, NotificationsPopover) |
| **lib/api/** | fetch 래퍼 + 도메인별 API 함수 |
| **lib/store/** | Zustand 전역 상태 (auth, chat 열림/스코프, theme) |
| **lib/status.ts** | 봉우리 상태 표시용 단일 소스 (label/color/pill) |

## 4. 요청 흐름 — 일반 페이지 로드

```
1.  사용자가 /plants 로 진입
2.  AppLayout이 마운트
    └─► supabase.auth.onAuthStateChange 구독 → 세션(access token) 확보
        └─► apiGet("/me")로 사용자 로드 후 authStore.setSession
        └─► 토큰 확보 즉시 prefetchAll()로 4개 쿼리 캐시 워밍
3.  PlantsPage 마운트 (enabled: !!accessToken 가드)
    └─► useQuery(["plants",...]) → apiGet("/plants?sort=activity")
    └─► useQuery(["buds",{}])    → apiGet("/buds")
4.  데이터 도착 시 PlantCard 그리드 렌더
5.  카드 클릭 → router.push(`/plants/${id}`)
```

## 5. 요청 흐름 — AI 채팅 (SSE)

```
1.  사용자가 ChatPanel에서 "취업·건강 식물 만들고 봉우리 추가" 입력
2.  streamChat() 호출 → POST /api/v1/chat/message (Bearer 토큰)
3.  FastAPI:
    a. require_user → User 객체
    b. _resolve_api_key → DB의 암호화된 키 복호화 (없으면 .env 키)
    c. LLMClient 인스턴스화 + 서비스 묶음 + ChatOrchestrator
    d. StreamingResponse(generate(), media_type="text/event-stream")
4.  ChatOrchestrator.run() (제너레이터):
    Step 1:
      ┌─ event: start
      └─ LLM.chat(history, tools, system_prompt)
         ↓ Gemini가 think 스킬 호출 결정
      ┌─ event: tool_call  {name: "think", ...}
      └─ registry.dispatch("think", ...) → SkillResult
      ┌─ event: tool_result
      └─ working_history 에 tool_use + tool_result 추가
    Step 2~N: 같은 방식으로 match_plant → create_plant → ...
    최종:
      └─ event: token (단어 단위)
      └─ event: done
5.  브라우저는 reader.read() 루프로 청크를 받아 onToken/onToolResult 콜백 호출
6.  스킬 결과에 따라 invalidateQueries로 영향받는 화면을 자동 재페치
```

이 멀티스킬 체인이 단일 사용자 발화에 대해 자동으로 작동하는 것이 본 MVP의 핵심 가치입니다.
자세한 내용은 `04_AI_Chat_And_Skills.md` 참고.

## 6. 외부 통합

| 외부 서비스 | 무엇으로 통신 | 누가 호출 | 키 보관 |
|-------------|--------------|-----------|---------|
| Google Gemini API | `google-genai` SDK (REST) | `LLMClient` | 사용자별 암호화 (Fernet, key = `KEY_ENCRYPTION_SECRET` SHA-256) |

LLM 키는 두 경로에서 들어옵니다.
1. `User.encrypted_api_key` — 설정 → AI → Gemini API 키 입력 시 저장.
2. `settings.llm_api_key` — `.env` 의 `LLM_API_KEY` (개발자/관리자 fallback).

`_resolve_api_key()` 가 1번 → 2번 순서로 시도.

## 7. 인증 모델

인증은 **Supabase Auth (Google OAuth)** 가 담당합니다. 자체 비밀번호/리프레시 토큰
구현은 없습니다.

| 토큰 | 저장 위치 | 만료/갱신 |
|------|-----------|-----------|
| Access (Supabase JWT) | `@supabase/supabase-js`(localStorage) | Supabase가 자동 갱신 |

- 프론트엔드는 `supabase.auth.onAuthStateChange` 로 세션을 받아 `authStore` 에 보관하고,
  요청마다 `Authorization: Bearer <Supabase JWT>` 를 붙입니다.
- 백엔드 `deps.require_user()` 는 JWT를 **ES256(JWKS 엔드포인트의 EC 공개키)** 으로 검증하고,
  실패 시 **HS256 legacy secret** 으로 fallback 검증합니다 (`audience="authenticated"`).
- 프로필이 없으면 토큰의 `sub`/`email`/메타데이터로 `profiles` 행을 자동 생성합니다.
- 관리자 API는 `require_admin` 의존성으로 `profiles.role == "admin"` 을 추가 검사합니다.
- `apiFetch()` 가 401을 만나면 Supabase 세션 갱신 콜백을 호출해 토큰을 재발급한 뒤
  같은 요청을 한 번 재시도합니다 — 사용자에게는 끊김 없이 보입니다.

## 8. 스케줄러

`scheduler/jobs.py` — APScheduler `BackgroundScheduler` 가 10분마다
`TransitionService.scan_all(db)` 를 실행.

작업 내용:
1. 활성 봉우리(bud/flower/fruit)가 `wilting_days` 동안 변화 없으면 `wilting` 으로 전이 + 알림.
   (legacy `seed` 행도 마이그레이션 004 이전 데이터 호환을 위해 함께 스캔)
2. `wilting` 상태로 `rot_disappear_days` 경과 시 `rot` + `disappeared_at` 설정 + 알림.
3. **식물 단위 시듦**: 한 식물의 시든 봉우리가 `plant_wilt_threshold` 개 이상이고
   임계 도달 후 `plant_wilt_days` 경과 시 식물 자체를 `wilting` 으로 전이 + 알림 (소생 불가).
4. 마감일이 `deadline_warn_days` 이내인 활성 봉우리에 `deadline_warning` 알림
   (중복 발송 방지: 미확인 알림이 있으면 건너뜀).

시간 기준은 타임 트래블 오프셋을 반영하는 `rs.now()`/`rs.today()` 를 사용합니다.
스케줄러는 `lifespan` 컨텍스트에서 앱 시작 시 켜고, 종료 시 `shutdown()` 호출.

## 9. 로그

채팅 한 턴의 전체 컨텍스트가 **Supabase `ai_logs` 테이블**(마이그레이션 `002_ai_logs`)에
저장되며, `backend/logs/chat/` 에 동일 내용의 JSON 파일이 미러로도 남습니다.
파일 이름: `YYYYMMDD_HHMMSS_<user_id 앞 8자>.json`

내용:
- 사용자 입력
- 시스템 프롬프트 전체
- 매 LLM 호출의 messages·tools 카운트·result_text·result_tool_use
- 매 스킬 호출의 args·data·ok 결과
- LLM(Gemini) 오류 (`llm_errors[]` — 종류·원인·원문)
- 이벤트 타임라인

관리자 AI 로그 페이지(`/admin/logs`)가 이 데이터를 표시합니다. `ai_logs` 테이블이
비어 있거나 없을 때는 파일 미러에서 읽어 표시합니다. 디버깅과 프롬프트 튜닝의 핵심 자료.
