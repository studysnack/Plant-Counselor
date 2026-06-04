# Plant Counselor — 시스템 테스트 계획서

본 문서는 Plant Counselor MVP의 동작 검증을 위한 시스템 테스트 명세입니다.
모든 케이스는 백엔드 `http://localhost:8000` + 프론트엔드 `http://localhost:3000`을
띄운 상태에서 수동으로 또는 Playwright로 재현 가능해야 합니다.

---

## 0. 환경 준비

| 항목         | 값                                          |
|--------------|---------------------------------------------|
| 백엔드        | `cd backend && poetry run python run.py`    |
| 프런트엔드    | `cd frontend && npm run dev` (Next.js 16)   |
| 테스트 계정   | Google 계정 (Supabase Google OAuth)         |
| LLM 키       | 설정 → AI 에서 Gemini API 키 입력         |

`/api/v1/health` 가 200 OK 를 반환하고 사이드바·홈 페이지가 로드되면 환경 OK.
(DB는 Supabase PostgREST HTTP로 접근하므로 로컬 DB는 필요 없습니다.)

---

## 1. 인증 & 세션

인증은 Supabase Auth(Google OAuth)로 단일화되어 있으며, 자체 닉네임/비밀번호 가입은 없습니다.

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| AUTH-1 | `/login` 에서 "Google로 계속하기" 클릭 → Google 동의 | `/home` 진입, 사이드바·홈 정상 |
| AUTH-2 | 로그인 후 새로고침 | Supabase 세션 자동 복구 (`onAuthStateChange`) |
| AUTH-3 | 액세스 토큰 만료 상태로 API 호출 | `apiFetch`가 401 받고 Supabase refresh → 재시도 후 정상 응답 |
| AUTH-4 | 설정 → 로그아웃 (`supabase.auth.signOut`) | 세션 클리어, `/login` 으로 리다이렉트 |
| AUTH-5 | 관리자(`zanviq.dev@gmail.com`) 로그인 | `role === "admin"` → `/admin` 으로 리다이렉트 |

## 2. 식물 (Plant) CRUD

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| PLT-1 | AI에게 "동아리 식물 만들어줘" | `create_plant` 스킬 호출, 정원/홈에 즉시 노출 |
| PLT-2 | 같은 분야 재요청 | `match_plant` 가 기존 식물 반환, 중복 미생성 |
| PLT-3 | 식물 상세 → "식물 삭제" → "정말 삭제" | 정원에서 제거, 통계 갱신 |
| PLT-4 | 정원 페이지 검색창에 "건강" 입력 | 클라이언트 필터로 매칭 카드만 표시 |
| PLT-5 | 정렬 토글: 최근 활동 / 활성순 / 생성순 | 카드 순서 변경, 콘솔 에러 없음 |

## 3. 봉우리 (Bud) 라이프사이클

봉우리 생애주기: `bud`(새싹) → `flower`(진행률 60%) → `fruit`(85%) → `harvested`(100% 수확).
방치 시 `wilting`(시들음, 갈색) → `rot`(썩음). 시든 봉우리는 다시 성장하지 않습니다(no-revival).
씨앗(seed) 상태는 제거되어 봉우리는 처음부터 `bud` 로 생성됩니다.

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| BUD-1 | "면접 준비 봉우리 만들어줘" | `create_bud` 호출, 상태 `bud` 로 식물 상세에 표시 |
| BUD-2 | 봉우리 행 클릭 → 드로어 오픈 | 진행률·메타·이력 모두 표시 |
| BUD-3 | 드로어 진행률 슬라이더 조정 | `update_bud_progress` 반영, 진행률 갱신 |
| BUD-4 | 진행률 60% / 85% 도달 | 자동 전이: 상태가 각각 `flower` / `fruit` 으로 변경 |
| BUD-5 | 진행률 100% 후 드로어 "수확" 클릭 | `harvest_bud` 호출, 통계의 "이번 달 수확" +1, 수확 바구니로 이동 |
| BUD-6 | 드로어 "포기" 클릭 | `abandon_bud` 호출, 상태 `rot` |
| BUD-7 | "마감일 5월 30일로 설정" | `set_deadline` 호출, 캘린더에 도트 표시 |
| BUD-8 | "면접 봉우리를 취업 식물로 옮겨줘" | `PATCH /buds/{id}/move`, 대상 식물로 이동 |

## 4. AI 채팅 & 멀티스킬

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| CHAT-1 | 홈/정원/캘린더 우상단 "AI 대화" 버튼 클릭 | 채팅 패널 우측에서 슬라이드인, 열린 동안 버튼은 숨김 |
| CHAT-2 | "취업이랑 건강 식물 두 개 만들어줘" | think → match_plant×2 → create_plant×2 가 한 응답에서 자동 실행 |
| CHAT-3 | "정원 현황 분석 후 시들고 있는 봉우리 모두 처리해줘" | get_garden_briefing → list_buds → update_bud_status×N 체인 |
| CHAT-4 | 식물 상세 → "이 식물 상담" | 브레드크럼이 "전체 › 건강"으로 변경, 히스토리 격리 |
| CHAT-5 | `/clear` | 현재 화면의 메시지만 비움 (DB 기록은 유지) |
| CHAT-6 | `/plants` | 인라인 식물 목록 카드 렌더 |
| CHAT-7 | `/skills` | 20개 스킬 목록 표시 |
| CHAT-8 | `/use get_garden_briefing` | 해당 스킬 실행 후 브리핑 응답 |
| CHAT-9 | LLM이 빈 응답을 반환할 때 | "응답이 비어있어요. 다시 시도해 주세요." 폴백 메시지 |
| CHAT-10 | 사용자 API 키 미설정 시 챗 | "API 키가 설정되지 않았습니다…" 친절 안내 |

## 5. 장기 사용 / 대량 데이터 (Stress)

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| STR-1 | 식물 10개 × 봉우리 각 20개(=200개) 생성 | 정원/홈 페이지 ≤ 1초 내 렌더, JS 메모리 누수 없음 |
| STR-2 | 대화 200턴 누적 후 새 메시지 전송 | history limit=20 로 잘림, 응답 정상 |
| STR-3 | 캘린더에서 한 해를 앞뒤로 12회 전환 | 매월 별도 쿼리, 결과 캐시(staleTime 30초) |
| STR-4 | 스케줄러 transition_scan (`scheduler_interval_minutes`, 기본 10분 주기) | wilting/rot/deadline 알림 자동 생성. 컨트롤러 타임 트래블로 즉시 검증 가능 |
| STR-5 | 봉우리 하나에 history 50건 누적 | 드로어 이력 영역 스크롤, 페이지 멈춤 없음 |

## 6. UI / 그래픽

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| UI-1 | 라이트 → 다크 모드 전환 | 모든 페이지의 배경/텍스트/카드가 즉시 반영, 새로고침에도 유지 |
| UI-2 | 시스템 모드 + OS 다크 토글 | `prefers-color-scheme` 변경 감지하여 자동 전환 |
| UI-3 | 정원 페이지 줌 인/아웃 (줌 컨트롤) | 벡터 정원 보드가 확대/축소, 식물·봉우리 배치 유지 |
| UI-4 | 브라우저 새로고침 시 첫 페인트 | 테마가 깜빡임 없이 즉시 적용 (layout.tsx 인라인 `pc-theme-init` 스크립트, `data-theme` 설정) |
| UI-5 | 채팅 입력 포커스 | 보더 색이 accent, 포커스 링 표시 |
| UI-6 | 사이드바 hover | 우측에 툴팁 노출 |
| UI-7 | 키보드 접근성 | Tab으로 모든 인터랙티브 요소 순회 가능, focus-visible 링 표시 |
| UI-8 | 반응형 | viewport 768px 이하에서 로그인 좌측 패널 숨김 (`hidden lg:flex`) |
| UI-9 | 수확 바구니 (정원 좌측) | 수확한 열매가 식물별로 쌓여 표시, 사이드바 필터·기록 팝업 동작 |

## 7. 알림

| ID | 시나리오 | 기대 결과 |
|----|----------|-----------|
| NOT-1 | 사이드바 종 아이콘 클릭 | popover 열림 |
| NOT-2 | "모두 읽음" 클릭 | 모든 알림 ack 처리, 배지 사라짐 |
| NOT-3 | 한 알림의 X 클릭 | 해당 알림만 ack |
| NOT-4 | popover 바깥 클릭 / Escape 키 | popover 닫힘 |

---

## 8. 자동화 가능 회귀 케이스 (Playwright)

`scripts/e2e.spec.ts` 를 추가하면 다음을 자동 검증할 수 있습니다(향후 작업):

1. `AUTH-1` ~ `AUTH-5`
2. `CHAT-2` 멀티스킬 체인 — AI 로그(`app/ai/log_store.py`)의 스킬 호출 횟수로 검증
3. `UI-1` ~ `UI-2` 테마 전환 후 `document.documentElement.getAttribute("data-theme")` 확인
