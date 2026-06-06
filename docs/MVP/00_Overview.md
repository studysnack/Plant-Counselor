# Plant Counselor MVP — 프로젝트 개요

## 1. 한 줄 정의

> **"고민과 일정을 식물 생애주기에 비유해 함께 가꾸는 AI 정원사."**

사용자가 자연어로 고민·일정·할 일을 말하면 AI 정원사가 이를 **식물(Plant)** 과 **봉우리(Bud)** 의 메타포로 시각화·관리합니다. 봉우리는 새싹(bud)에서 시작하여 성장하고, 결실을 맺어 수확하거나, 방치되면 시들고 썩습니다.

---

## 2. 핵심 모델

| 개념                 | 역할                   | 예시                                                      |
| ------------------ | -------------------- | ------------------------------------------------------- |
| **식물 (Plant)**     | 분야·카테고리 컨테이너         | "취업", "동아리", "운동", "일상"                                 |
| **봉우리 (Bud)**      | 식물에 속한 구체적 고민·일정·할 일 | "면접 준비", "도호랑 밥먹기", "주 3회 운동"                           |
| **상태 (Status)**    | 봉우리의 생애주기 6단계        | bud → flower → fruit → harvested / wilting → rot |
| **진행률 (Progress)** | 0~100%, 자동 상태 전이 트리거 | 60% → flower, 85% → fruit                    |
| **타입 (Type)**      | 봉우리의 성격 구분           | concern(고민/걱정) / schedule(일정/할일/약속)                     |

### 상태 전이 규칙

```
                  ┌─────────┐
                  │   bud   │ (0~59%, 새싹)
                  └────┬────┘
                       │ 진행률 60%+
                  ┌────▼────┐
                  │ flower  │ (60~84%)
                  └────┬────┘
                       │ 진행률 85%+
                  ┌────▼────┐
                  │  fruit  │ (85~100%)
                  └────┬────┘
                       │ 진행률 100% + harvest_bud 스킬
                  ┌────▼────┐
                  │harvested│ ── 수확 완료!
                  └─────────┘

  (N일 활동 없음)        (N일 추가 방치)
  ┌─────────┐            ┌──────┐
  │ wilting │ ──────────▶ │ rot  │ ── 썩음
  └─────────┘            └──────┘
```

- **씨앗(seed) 단계 제거**: 마이그레이션 `004_remove_seed_bud_status`에서 seed 상태 폐기. 봉우리는 새싹(bud)으로 생성됨
- **자동 전이**: `wilting_days`(기본 7일) 동안 진행 없으면 wilting, 추가 `rot_disappear_days`(14일) 후 rot
- **수동 전이**: `update_bud_status` 스킬로 직접 변경 가능
- **진행률 기반 전이**: `update_bud_progress` 호출 시 60/85% 임계에서 자동 승격 (flower/fruit)
- **수확**: `harvest_bud`로 완료 처리 → harvested 상태 (진행률 100% 필요)
- **포기**: `abandon_bud`로 포기 → rot 상태
- **소생 불가**: 시든(wilting/rot) 봉우리 또는 시든 식물의 봉우리는 더 이상 성장할 수 없음 (대화만 가능)

---

## 3. MVP 기능 목록

### 3.1 인증 시스템
- Supabase Auth 기반 **Google OAuth** 로그인 (자체 비밀번호 인증 없음)
- 백엔드는 Supabase가 서명한 JWT를 **ES256(JWKS)** 으로 검증 (HS256 legacy fallback)
- 401 시 Supabase 세션 자동 갱신 → 재시도 (사용자에게 끊김 없음)
- 계정 삭제 시 전체 데이터 cascade 삭제 + Supabase Auth 사용자 삭제
- 관리자 역할(`profiles.role`) 시스템 — admin 계정은 로그인 시 `/admin`으로 이동

### 3.2 식물(Plant) 관리
- AI 대화로 식물 생성 (분야 자동 추론 + 중복 검사)
- 정원 페이지: **그래픽 뷰**(픽셀아트 스프라이트 + 가로 스크롤 캐러셀) + **리스트 뷰**(검색/정렬)
- 식물 상세: 통계(활성/수확/포기) + 봉우리 목록(필터) + 삭제(2단계 확인)

### 3.3 봉우리(Bud) 관리
- AI 대화로 봉우리 생성 (고민/일정 자동 구분, 마감일 자동 설정)
- 봉우리 드로어: 진행률 바·메타정보·상태 변경 이력
- 빠른 액션: +20% / 수확 / 포기 버튼 (AI 자동 호출)
- 가지 끝에 봉우리 스프라이트로 시각화, hover 시 이름 표시

### 3.4 AI 정원사 채팅
- **ReAct 멀티스텝 루프**: 한 번의 발화로 여러 스킬 연속 실행 (최대 10스텝, 런타임 조정 가능)
- **20개 스킬**: think, match_plant, create_plant, delete_plant, create_bud, update_bud_status, update_bud_progress, set_deadline, abandon_bud, harvest_bud, list_plants, list_buds, get_statistics, get_garden_briefing, search_conversation, suggest_scope_change, create_calendar_event, list_calendar_events, update_calendar_event, delete_calendar_event
- **4가지 대화 스코프**: 전체(global), 식물(plant), 봉우리(bud), 캘린더(calendar)
- **세션별 권한**: 스코프에 따라 수정·삭제 가능 범위 제한 (global=전체, plant/bud=자기 것, calendar=일반 일정)
- **명령어**: /clear(화면 비움), /delete(현재 세션 기록 DB 삭제) 등
- **응답 톤**: 설정에서 선택한 톤이 시스템 프롬프트에 반영됨
- **스킬 실행 후 자동 캐시 갱신**: 식물/봉우리/통계/캘린더/브리핑 쿼리 자동 무효화
- **드래그 리사이즈**: 채팅 패널 폭 조절 가능 (280~700px, 저장됨)
- SSE 실시간 스트리밍 (토큰 단위)

### 3.5 캘린더 & 일정
- 월별 그리드 캘린더 (이벤트 도트, 선택일 상세)
- 봉우리 마감일 + **독립 일정**(`calendar_events` 테이블) 병합 표시 (`source: "bud" | "event"`)
- 이벤트에 식물 이름·시간(detail)·타입(일정/고민) 표시
- 캘린더 페이지 "일정 추가" 모달 (제목/날짜/관련 식물)
- 캘린더 전용 채팅 스코프 (`kind: "calendar"`) — 공유 "AI 대화" 버튼으로 진입
- AI 일일 브리핑 (매 호출 재생성)
- 일정 생성 시 AI가 식물 자동 매칭·생성 (질문 없이)
- 인접 월 프리페치 (‹/› 클릭 즉시 응답)

> 공유 **"AI 대화"** 버튼(`components/chat/AiChatButton.tsx`)이 홈·정원·캘린더 우상단에 표시되며, 채팅 패널이 열려 있는 동안에는 숨겨집니다.

### 3.5.1 대화 기록 브라우저
- 모든 대화를 global → calendar → 식물 → 봉우리 계층으로 탐색
- 식물/봉우리 이름 해석, 키워드 검색, 스레드 내 검색
- "이 대화 이어가기" → 해당 스코프로 채팅 재개

### 3.6 알림
- 시들·썩음·마감 임박 자동 알림 (10분 주기 스케줄러)
- 사이드바 배지 + 팝오버 (읽음/모두읽음)

### 3.7 테마 시스템
- **3가지 모드**: light / dark / system (OS 추종)
- 팔레트는 크림/올리브 단일 토큰셋 (강조색 = `--accent` 올리브 고정)
- **Pre-hydration**: `theme-init.js`로 첫 페인트 깜빡임 방지
- **Persist**: localStorage(`pc-theme`)에 저장, 새로고침 후에도 유지

### 3.8 설정
- 계정: 닉네임/이메일 표시, 로그아웃(Supabase signOut), 계정 삭제
- AI: Gemini API 키 (Fernet 암호화 저장), 응답 톤 3종
- 정원 규칙: 시듦 기준 일수, 썩음 일수, 마감 알림 기준 (NumberStepper)
- 테마: 모드 + 강조색 (시각적 프리뷰 카드)
- 정보: 버전, 데이터 정책

---

## 4. 기술 스택

| 계층    | 기술                                                                                             |
| ----- | ---------------------------------------------------------------------------------------------- |
| 프론트엔드 | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, Zustand, TanStack Query v5 |
| 백엔드   | FastAPI, **supabase-py** (PostgREST HTTP — SQLAlchemy/psycopg2 미사용), Pydantic v2, APScheduler |
| DB    | **Supabase PostgreSQL** + Row Level Security (supabase-py HTTP 접근)                              |
| LLM   | Google Gemini (`google-genai` SDK; 코드 기본 모델 `gemini-3-flash-preview`, `profiles.ai_model` 기본값 `gemini-2.5-flash`) |
| 인증    | Supabase Auth (Google OAuth) + **ES256 JWKS** 검증 (HS256 fallback) + Fernet API 키 암호화          |
| ID    | ULID (python-ulid)                                                                              |
| 스프라이트 | Python Pillow — 자동 생성·crop·좌표 매핑                                                               |

---

## 5. 디렉터리 구조

```
plant-counselor/
├── backend/
│   ├── app/
│   │   ├── ai/                    ─ AI 엔진
│   │   │   ├── chat_orchestrator.py  ─ ReAct 루프 + SSE 스트리밍
│   │   │   ├── llm_client.py         ─ Gemini SDK 어댑터 (오류 분류·기록)
│   │   │   ├── prompt_builder.py     ─ 시스템 프롬프트 조립 (rs.today())
│   │   │   ├── skill_registry.py     ─ 스킬 등록·디스패치
│   │   │   ├── permissions.py        ─ 세션별 수정·삭제 권한
│   │   │   ├── log_recorder.py       ─ 채팅 JSON 로그 + Supabase ai_logs
│   │   │   └── skills/               ─ 20개 스킬 모듈
│   │   ├── db/
│   │   │   └── supa.py               ─ Supabase PostgREST 클라이언트 싱글톤
│   │   ├── repositories/          ─ supabase-py DB CRUD
│   │   ├── services/              ─ 비즈니스 로직
│   │   ├── schemas/               ─ Pydantic 스키마
│   │   ├── routers/               ─ FastAPI 엔드포인트 (chat, plants, buds,
│   │   │                            calendar(stats), me, notifications,
│   │   │                            conversations, admin, public)
│   │   ├── scheduler/jobs.py      ─ 10분 주기 봉우리 자동 전이
│   │   ├── runtime_settings.py    ─ 런타임 변수(모델·스텝·타임 오프셋 등)
│   │   ├── config.py              ─ 환경설정 (.env, pydantic-settings)
│   │   ├── deps.py                ─ get_db + require_user/require_admin (JWKS)
│   │   └── main.py                ─ FastAPI 앱 진입점 (CORS 멀티 오리진)
│   ├── migrations/                ─ Supabase 적용 SQL (001~006)
│   ├── logs/chat/                 ─ 채팅 디버그 로그 (JSON)
│   └── run.py                     ─ uvicorn 실행
├── frontend/
│   ├── app/
│   │   ├── layout.tsx + providers.tsx   ─ 루트 레이아웃 + 테마 부트스트랩
│   │   ├── globals.css                 ─ 디자인 토큰 + 컴포넌트 프리미티브
│   │   ├── page.tsx                    ─ 랜딩 페이지 "/"
│   │   ├── (auth)/login/page.tsx       ─ Google OAuth 로그인
│   │   ├── admin/                      ─ 관리자 패널 (role=admin)
│   │   │   ├── page.tsx · users/ · logs/ · notifications/ · data/ · controller/
│   │   └── (app)/
│   │       ├── layout.tsx              ─ 사이드바 + ChatPanel + prefetchAll()
│   │       ├── home/page.tsx           ─ 홈 (통계 + 식물 보드 + 시듦)
│   │       ├── plants/page.tsx         ─ 정원 (그래픽/리스트 토글)
│   │       ├── plants/[id]/page.tsx    ─ 식물 상세 + 봉우리 드로어
│   │       ├── calendar/page.tsx       ─ 캘린더 + 일정 관리
│   │       ├── history/page.tsx        ─ 대화 기록 브라우저 (2-패널)
│   │       └── settings/page.tsx       ─ 설정 5탭
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatPanel.tsx           ─ AI 채팅 패널 (SSE + 명령어)
│   │   │   └── AiChatButton.tsx        ─ 공유 "AI 대화" 버튼
│   │   ├── plants/
│   │   │   ├── GardenPlantVisual.tsx   ─ 픽셀아트 정원 식물 렌더
│   │   │   └── BudDetailDrawer.tsx     ─ 봉우리 상세 드로어
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx             ─ 사이드바 (어두운 올리브)
│   │   │   └── NotificationsPopover.tsx ─ 알림 팝오버
│   │   └── ui/Skeleton.tsx             ─ 로딩 스켈레톤
│   ├── lib/
│   │   ├── api/                        ─ fetch 래퍼 + 도메인 함수 (admin 포함)
│   │   ├── store/                      ─ Zustand 스토어 3개 (auth, chat, theme)
│   │   ├── markdown.tsx                ─ 자체 마크다운 렌더러
│   │   └── supabase.ts                 ─ Supabase 클라이언트
│   └── public/
│       ├── sprites/                    ─ 픽셀아트 스프라이트
│       └── theme-init.js              ─ Pre-hydration 테마
├── render.yaml                    ─ Render 백엔드 배포 설정
├── scripts/
│   └── generate_pixel_sprites.py  ─ 스프라이트 생성기
└── docs/
    └── MVP/                       ─ 이 문서 묶음
```

---

## 6. 문서 목차

| 번호 | 제목 | 무엇을 다루는가 |
|------|------|----------------|
| 00 | **이 문서** | 개요·모델·기능·스택·구조 |
| 01 | Architecture | 계층·요청 흐름·외부 통합·인증·스케줄러 |
| 02 | UI Pages & Components | 페이지/컴포넌트 상세 명세 |
| 03 | Theme System | 디자인 토큰·테마 전환·사용 가이드 |
| 04 | AI Chat & Skills | ReAct 루프·20개 스킬·프롬프트 설계·멀티스킬 |
| 05 | Backend Code Walkthrough | **모든 Python 파일/함수/변수/설계 이유** |
| 06 | API Reference | REST 엔드포인트 전체 명세 |
| 07 | System Test Plan | 시스템 테스트 케이스 60+ |
| 08 | Operations | 실행·환경변수·마이그레이션·운영 |
| 09 | Summary (요약) | 전체 요약 + 핵심 흐름 |
