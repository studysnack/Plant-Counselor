# 04. AI 채팅 & 스킬

## 1. 아키텍처 개요

```
사용자 발화 ("오늘 오후 1시에 도호랑 밥먹기")
   │
   ▼
ChatOrchestrator.run()
   │ ── 시스템 프롬프트(정원 현황 + 행동 규칙)
   │ ── 대화 이력(limit=20)
   │ ── 스킬 카탈로그(20개)
   │
   ▼  ReAct 루프 (MAX_STEPS=runtime_settings, 기본 10)
   ┌──────────────────────────────────┐
   │ Step 1: LLM → think("계획 수립") │
   │ Step 2: LLM → match_plant("일상")│
   │ Step 3: LLM → create_plant(...)  │
   │ Step 4: LLM → create_bud(...)    │
   │ Step 5: LLM → 최종 텍스트 응답    │
   └──────────────────────────────────┘
   │
   ▼
SSE 스트리밍 (token 이벤트)
   │
   ▼
프론트: invalidateQueries → UI 자동 갱신
```

## 2. ReAct 루프 상세 (`chat_orchestrator.py`)

```python
MAX_STEPS = 10  # 코드 상수는 fallback. 실제 값은 매 실행마다 runtime_settings에서 읽음
                # _max_steps = rs.get("llm_max_steps", MAX_STEPS)

for step in range(_max_steps):
    result = llm.chat(working_history, catalog, system)
    text, tool_use = result["text"], result["tool_use"]

    # 빈 응답 1회 재시도
    if not text and not tool_use:
        result = llm.chat(working_history, catalog, system)
        text, tool_use = result["text"], result["tool_use"]

    if tool_use:
        # 스킬 실행
        yield "event: tool_call"
        skill_result = registry.dispatch(tool_use["name"], tool_use["input"], ctx)
        yield "event: tool_result"

        # 결과를 history에 추가 → 다음 LLM 호출이 이전 결과를 봄
        working_history += [
            {"role": "assistant", "content": [{"type": "tool_use", ...}]},
            {"role": "user", "content": [{"type": "tool_result", ...}]}
        ]
        continue  # 다음 스텝

    break  # 텍스트 응답 → 루프 종료

# MAX_STEPS 소진 시 강제 텍스트 호출
if not response_text:
    result = llm.chat(working_history, [], system)  # 도구 없이
    response_text = result.get("text") or "작업을 완료했습니다."
```

핵심 설계:
- **working_history에 도구 결과 누적**: 매 스킬 호출 후 assistant(tool_use) + user(tool_result)를 history에 추가하여, 다음 LLM 호출이 이전 결과(예: plant_id)를 볼 수 있음
- **빈 응답 가드**: Gemini가 function_call만 반환하고 text를 비우는 경향이 있어 1회 재시도
- **MAX_STEPS 안전망**: 스텝 소진(기본 10, `runtime_settings.llm_max_steps`에서 변경 가능) 후 강제로 도구 없이 텍스트 요청

## 3. 시스템 프롬프트 (`prompt_builder.py`) 전체 구조

프롬프트는 여러 섹션으로 조립됩니다(정체성/응답 톤/정원 현황/핵심 모델/행동 원칙/행동 규칙/세션 권한/응답 형식):

### 3.1 정체성 & 컨텍스트
```
당신은 Plant Counselor의 AI 정원사입니다.
오늘 날짜: 2026-05-24
현재 화면: 캘린더
현재 상담 식물/세션: ...   ← plant/bud 스코프일 때만 추가
```
- 오늘 날짜는 `rs.today()`(타임 트래블 오프셋 반영)로 채워짐
- `current_screen`이 "캘린더"면 일정 중심 응답, "홈"이면 전체 정원 중심
- plant/bud 스코프면 현재 상담 중인 식물·봉우리 컨텍스트 라인이 추가되어, AI가 off-topic 요청을 감지하고 세션 변경을 제안할 수 있음

### 3.1b 응답 톤 (`## 응답 톤`)
```
## 응답 톤 (사용자 설정 — 모든 답변에 일관 적용)
{tone_guide}
```
- 사용자 설정의 **톤**(counselor / assistant / friend)이 실제로 적용됨
- `chat.py`가 `user.tone`을 읽어 `orchestrator.run(tone=...)` → `build_system(tone=...)`로 전달
- `prompt_builder._TONE_GUIDE`가 톤별 지시문을 매핑 (기본값 `counselor`)
  - counselor: 따뜻한 상담사 존댓말
  - assistant: 담백한 비서 존댓말
  - friend: 친한 친구 반말
- 말투와 무관하게 스킬 실행·정보 정확성은 동일하게 유지

### 3.2 정원 현황
```
활성 고민: 3개 | 활성 일정: 4개
시들고 있는 봉우리: 0개 | 이번 달 수확: 2개
식물 목록:
  - [01KSAR86] 취업: 취업 관련 목표와 할 일
  - [01KSAR89] 건강: 건강 관리 목표와 할 일
```
- 실시간 통계와 식물 목록(최대 10개)을 프롬프트에 주입

### 3.3 핵심 모델 설명
- 식물 = 분야/카테고리
- 봉우리 = 구체적 고민/일정
- 상태 전이 규칙

### 3.4 행동 원칙 (가장 중요)

**즉시 실행 — 묻지 않는다**
- 의도가 파악되면 확인 없이 즉시 스킬 호출
- "어떤 식물에 추가할까요?" 같은 질문 금지

**질문 금지**
- "~할까요?" 같은 확인 질문 하지 않음
- 부족한 정보는 문맥에서 합리적으로 추론
- 추론 불가능한 핵심 정보가 하나만 빠졌을 때만 한 문장 질문

**의도 판단**
- 특정 단어가 아닌 대화 문맥 전체로 판단
- 빈 응답 절대 금지

### 3.5 봉우리 탐색 규칙 (필수)

`update_bud_progress` / `update_bud_status` / `harvest_bud` / `abandon_bud` / `set_deadline` 호출 전:

```
1. 현재 대화에서 bud_id를 이미 알고 있으면 바로 사용
2. bud_id를 모르면 반드시 list_buds(plant_id=...) 먼저 호출
   - 식물 ID도 모르면 match_plant → list_buds 순서
3. 제목 부분 일치로 봉우리 탐색 (예: "팔굽혀펴기" → "매일 팔굽혀펴기 10개" 매칭)
4. 절대로 list_buds 없이 "봉우리가 없는 것 같아요" 금지
```

> **이유**: AI가 대화 문맥에서만 bud_id를 유추하려다 실패하여 "봉우리가 없습니다"라고 잘못 응답하는 버그가 있었음. list_buds 먼저 호출을 강제하여 해결.

### 3.6 일정 생성 규칙 (봉우리 vs 캘린더 일정 판단)

```
일정이나 약속이 언급되면 즉시:
1. 내용에서 분야를 추론 (밥먹기 → 일상, 면접 → 취업)
2. match_plant로 해당 분야 검색
3. 없으면 create_plant로 즉시 생성
4. 성격에 따라 둘 중 하나를 스스로 판단해 호출:
   - 단순 약속·예약·리마인더(진행률 추적 불필요)
     → create_calendar_event (plant_id 연결, date, detail)  ← 봉우리 없이 캘린더에만 표시
   - 진행을 추적할 목표·할 일
     → create_bud (type="schedule", detail에 시간, deadline에 날짜)
   - 날짜는 YYYY-MM-DD로 변환 (오늘/내일 자동 계산)
5. 절대로 "어떤 식물에 추가할까요?" 질문 금지
6. 모호하면(단순 일정인지 추적 목표인지 불분명) 한 문장으로만 물어봄
```

### 3.7 일정 조회 / 캘린더 화면 규칙
- 일정 조회("오늘 일정", "이번 주 일정" 등)는 **반드시 두 스킬을 모두 호출**한다:
  - `list_buds` — 식물 봉우리에 속한 일정(= "식물 일정")
  - `list_calendar_events` — 캘린더에 직접 추가한 순수 일정(= "일반 일정")
- 답변은 "일반 일정"과 "식물 일정"을 명확히 구분하여 설명
- 캘린더 화면에서 추가하는 일정은 기본적으로 create_calendar_event를 우선 고려

### 3.8 세션별 권한 (`permissions.py`)
프롬프트의 `## 세션별 권한` 섹션 + `app/ai/permissions.py`의 가드가 함께 동작:
- **global**: 모든 식물·봉우리·일정 생성·조회·수정·삭제 가능
- **plant / bud**: 자기 것(현재 식물/봉우리)만 수정·삭제 가능
- **calendar**: 일반 일정(calendar_events)만 수정·삭제. 봉우리는 생성(create_bud)·조회(list_buds)만 가능
- 권한 밖 작업은 변이 스킬의 `guard_*`가 자동 거부(forbidden) → AI는 시도 대신 세션 변경을 제안

### 3.9 응답 형식
- 스킬 실행 후: 한두 문장 자연스러운 안내
- 짧고 친근하게, **마크다운 문법으로 작성**(굵게/목록/소제목/백틱, 실제 줄바꿈)

## 4. 20개 스킬 상세

> 등록 순서(`chat.py` `_build_registry`): think, match_plant, create_plant, delete_plant,
> create_bud, update_bud_status, update_bud_progress, set_deadline, abandon_bud, harvest_bud,
> list_plants, list_buds, get_statistics, get_garden_briefing, search_conversation,
> suggest_scope_change, create_calendar_event, list_calendar_events,
> update_calendar_event, delete_calendar_event.
>
> (참고: `PATCH /buds/{id}/move`는 REST 엔드포인트일 뿐 채팅 스킬이 아니므로 위 목록에 없음)

### 4.1 think (메타 스킬)
- **목적**: 복잡 작업 전 계획 수립. DB 변경 없음.
- **왜 첫 번째로 등록**: LLM이 카탈로그에서 첫 번째로 보고, 복잡 요청 시 자연스럽게 선택
- **예시**: "동아리·운동·공부 3개 식물 만들고 봉우리 추가" → think로 계획 → 실행

### 4.2 match_plant (조회)
- **목적**: 중복 식물 방지. 항상 create_plant 전에 호출
- **내부**: `PlantService.find_matches(query)` → `LIKE %query%` SQL
- **반환**: `{matches: [{id, name, description}]}` — 비어있으면 새 식물 생성 필요

### 4.3 create_plant (변경)
- **필수 파라미터**: name, description
- **선택**: species(기본 tree_oak), color(기본 brand.primary_leaf)
- **내부**: `PlantService.create()` → ULID 생성 + flush + commit
- **프롬프트 지시**: description은 AI가 문맥에서 추론하여 채움

### 4.4 create_bud (변경)
- **필수**: plant_id, title, type("concern"/"schedule")
- **선택**: detail(시간 등 구체 정보), deadline(YYYY-MM-DD)
- **내부**: `BudService.create()` → 초기 상태 "bud" + BudHistory("→bud", "생성") 기록
  (씨앗(seed) 단계는 migration 004 이후 폐지됨)
- **deadline 파싱**: ISO 문자열 → `date.fromisoformat()`, 실패 시 None

### 4.5 update_bud_status (변경)
- **필수**: bud_id, to_status (6종 enum: bud / flower / fruit / harvested / wilting / rot — seed 없음)
- **내부**: from→to 이력 기록 + `last_progress_at` 갱신
- **소생 불가**: 이미 시든(wilting/rot) 봉우리 또는 시든 식물의 봉우리는 성장 상태로 되돌릴 수 없음(ValueError)
- **수확 가드**: `harvested`로의 전이는 진행률 100%일 때만 허용

### 4.6 update_bud_progress (변경)
- **필수**: bud_id, progress(0-100, clamp)
- **자동 전이 로직**: `_PROGRESS_TRANSITIONS = [(85, "fruit"), (60, "flower")]`
  - 내림차순 순회 → 첫 매칭이 가장 진행된 상태 (60%→flower, 85%→fruit)
  - 전이 발생 시 BudHistory 자동 기록
- **수확은 100% 달성 후 harvest_bud로** (progress 100이 자동 수확은 아님)
- **소생 불가**: 시든 봉우리/식물에서는 진행률을 올릴 수 없음(ValueError)

### 4.7~4.20 (기타)
- `delete_plant`: 식물 삭제 (봉우리·기록 cascade). 명확한 삭제 의사가 있을 때만
- `set_deadline`: YYYY-MM-DD 형식 검증 후 설정 (bud_id 필요 → 봉우리 탐색 규칙 적용)
- `harvest_bud` / `abandon_bud`: 각각 "harvested" / "rot" 상태로 변경
  (수확은 진행률 100%일 때만)
- `list_plants` / `list_buds`: 필터링된 목록 반환
- `get_statistics`: 분야·기간별 집계
- `get_garden_briefing`: 정원 전체 한 줄 요약 생성
- `search_conversation`: `LIKE %query%` 대화 검색 (와일드카드 이스케이프 처리)
- `suggest_scope_change`: 스코프(세션) 불일치 시 다른 식물/봉우리 세션으로 변경 제안
  (작업을 실행하지 않고 제안만 — 프론트가 직전 질문을 새 세션 입력창으로 이관)
- 캘린더 일정(봉우리와 별개의 순수 일정): `create_calendar_event` /
  `list_calendar_events` / `update_calendar_event` / `delete_calendar_event`

## 5. LLM 클라이언트 — Gemini ↔ Anthropic 변환

`google-genai` SDK는 메시지를 `contents[]`, 도구를 `function_declarations`로 받습니다.

내부적으로 Anthropic 형식(role + content blocks)을 중간 표현(IR)으로 사용:

| Anthropic IR | Gemini 변환 |
|-------------|------------|
| `{type:"tool_use", name, input, id}` | `{function_call: {name, args}}` |
| `{type:"tool_result", tool_use_id, content}` | `{function_response: {name, response}}` |
| Gemini의 `function_call` | → `{name, input: dict(args), id: name}` |

이 IR 덕분에 향후 Claude/OpenAI 등 다른 LLM으로 교체 시 어댑터만 변경하면 됩니다.

### Gemini 에러 처리 (재시도 + 분류 + 관리자 기록)
- **재시도**: 503/unavailable/overloaded/timeout 등 일시적 오류는 지수 백오프로 최대 3회 자동 재시도(`_is_retryable`)
- **사용자용 친절 메시지**(`_friendly_error`):
  - `503`/overloaded → "AI 모델이 일시적으로 혼잡합니다…"
  - `NOT_FOUND` → "모델을 사용할 수 없습니다."
  - `API_KEY_INVALID` → "API 키가 유효하지 않습니다."
  - `quota`/`rate`/`429` → "API 호출 한도를 초과했습니다."
- **관리자용 분류**(`_classify_error`): 종류 매핑 → overloaded(503) / rate_limit(429) /
  auth(401·403) / model_not_found(404) / timeout / other + 한국어 원인 설명 + raw 원문
- **기록**: 실패 시 `chat()`이 `error`/`error_kind`/`error_cause`를 반환 →
  `chat_orchestrator._record_llm_error` → `log_recorder.log_llm_error`가 세션 로그의
  `llm_errors[]`에 기록 → 관리자 AI 로그 페이지(`/admin/logs`)에 노출

## 6. 대화 스코프 시스템

| 스코프 | 진입 방법 | 대화 격리 | 프롬프트 차이 |
|--------|----------|----------|-------------|
| global | 공용 "AI 대화" 버튼(홈/정원/캘린더) | 전체 정원 대화 | current_screen=요청값(홈 등), 권한 전체 |
| plant | 식물 카드/상세 "상담" | 해당 식물만의 대화 | "현재 상담 식물" 컨텍스트 + 자기 식물만 수정 권한 |
| bud | 봉우리 상세 "상담" | 해당 봉우리만의 대화 | "현재 상담 세션(식물명+봉우리명)" 컨텍스트 + 자기 봉우리만 수정 권한 |
| calendar | 캘린더 화면 AI 대화 | 모든 일정 관련 대화 | current_screen="캘린더", 일반 일정만 수정 권한 |

각 스코프는 DB의 `Conversation` 테이블에서 `(user_id, scope, scope_id)` 유니크 제약으로 격리됩니다. 같은 사용자가 같은 식물에서 대화하면 항상 같은 conversation_id를 공유합니다.

## 7. SSE 이벤트 흐름

```
Frontend                           Backend (SSE)
────────                           ──────────────
POST /chat/message ──────────────► event: start {message_id}
                                   │
                                   ├─ event: tool_call {name, args}
                                   ├─ event: tool_result {name, result}
                                   │   (반복: 최대 MAX_STEPS회, 기본 10)
                                   │
                                   ├─ event: token {text: "운"}
                                   ├─ event: token {text: "동 "}
                                   ├─ event: token {text: "식물을 "}
                                   │   (단어별 스트리밍)
                                   │
                                   └─ event: done {}
```

프론트는 `streamChat()` 에서 SSE 파서로 각 이벤트를 받아:
- `onToolCall`: UI에 스킬 호출 알림 (현재 숨겨짐)
- `onToolResult`: `dirtySkills` Set에 스킬명 추가
- `onToken`: 메시지 텍스트 누적
- `onDone`: `dirtySkills`에서 `SKILL_INVALIDATIONS` 매핑으로 쿼리 무효화

## 8. 스킬 → 쿼리 무효화 매핑

```javascript
const SKILL_INVALIDATIONS = {
  create_plant:          ["plants", "stats", "briefing"],
  delete_plant:          ["plants", "buds", "stats", "briefing"],
  create_bud:            ["buds", "plants", "stats", "briefing", "calendar"],
  create_calendar_event: ["calendar"],
  update_calendar_event: ["calendar"],
  delete_calendar_event: ["calendar"],
  update_bud_status:     ["buds", "plants", "stats", "briefing", "bud"],
  update_bud_progress:   ["buds", "bud"],
  harvest_bud:           ["buds", "plants", "stats", "briefing", "bud"],
  abandon_bud:           ["buds", "plants", "stats", "briefing", "bud"],
  set_deadline:          ["buds", "bud", "calendar", "stats"],
};
```

스킬 실행 후 관련 TanStack Query 캐시가 자동으로 무효화되어, 홈/정원/캘린더/식물상세 페이지가 즉시 갱신됩니다.

## 9. 검증된 멀티스킬 사례

### 사례 1: "동아리, 운동, 공부 식물 세 개 만들고 각각 봉우리 추가"
```
step 1: think("3개 식물+봉우리 계획")
step 2: match_plant("동아리") → 없음
step 3: create_plant("동아리") → id A
step 4: match_plant("운동") → 없음
step 5: create_plant("운동") → id B
step 6: match_plant("공부") → 없음
step 7: create_plant("공부") → id C
step 8: create_bud(A, "새 동아리 활동 기획")
step 9: create_bud(B, "주 3회 헬스장 방문")
step 10: create_bud(C, "자격증 시험 준비 시작")
final: "네, 동아리, 운동, 공부 식물을 만들고 각각 봉우리를 추가했어요!"
```

### 사례 2: "오늘 오후 1시에 도호랑 밥먹기" (캘린더 스코프)
```
step 1: match_plant("일상") → 없음
step 2: create_plant("일상", "일상 생활 일정")
step 3: create_bud(plant_id, title="도호랑 밥먹기", type="schedule",
                   detail="오후 1시, 도호와 함께", deadline="2026-05-24")
final: "도호랑 밥먹기 일정을 '일상' 식물에 추가했어요!"
→ 캘린더 24일에 도트 표시, "오늘 일정"에 카드 표시
```

## 10. 채팅 로그 (`log_recorder.py` + `log_store.py`)

모든 채팅 턴은 **Supabase `ai_logs` 테이블이 정본**으로 저장되고, 로컬 파일
(`backend/logs/chat/YYYYMMDD_HHMMSS_<user8>.json`)에 미러링됩니다(`log_store.save`).
DB가 가능하면 DB, 아니면 파일로 폴백 — Render 무료처럼 디스크가 휘발성인 환경에서도
로그가 살아남게 하기 위함입니다.

포함 내용:
- 사용자 입력 원문
- 시스템 프롬프트 전체
- 대화 이력(history)
- 매 LLM 호출의 messages + tools 카운트 + result
- 매 스킬 호출의 args + ok + message + data
- LLM 오류(`llm_errors[]`: kind / cause / raw error)
- 이벤트 타임라인

관리자 AI 로그 페이지(`/admin/logs`)는 이 데이터를 표시하며,
DB가 비어 있거나 없으면 파일 로그로 폴백합니다. 디버깅과 프롬프트 튜닝의 핵심 자료입니다.
