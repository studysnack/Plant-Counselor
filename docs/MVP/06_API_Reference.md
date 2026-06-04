# 06. API Reference

모든 응답은 `{ok: true, data: ...}` 또는 `{ok: false, error: {code, message}}` 형태입니다.
공통 prefix: `http://localhost:8000/api/v1`

## 인증 방식

별도의 `/auth/*` 엔드포인트는 없습니다. 인증은 **Supabase Auth(Google OAuth)** 가 담당하며,
프론트엔드가 발급받은 Supabase JWT를 `Authorization: Bearer <token>` 헤더로 보냅니다.
백엔드(`app/deps.py`)는 이 토큰을 **JWKS의 ES256/RS256 공개키**로 검증하고
(실패 시 `SUPABASE_JWT_SECRET` 기반 HS256으로 fallback), `audience="authenticated"` 를 확인합니다.

- `require_user` — 모든 보호 엔드포인트에서 사용. 토큰 검증 후 `profiles` 행을 반환(없으면 자동 생성).
- `require_admin` — `require_user` + `profiles.role == "admin"` 검사. 아니면 403.

## 사용자

### GET `/me` — 현재 프로필 (`UserOut`)
### PATCH `/me` — `UserUpdate` (nickname, tone, ai_model, garden_rules, appearance)
### DELETE `/me` — 회원탈퇴. body 없음. 전체 데이터 cascade 삭제 + Supabase Auth 사용자 삭제
### PUT `/me/api-key` — `{api_key}` (Fernet 암호화 저장)

> 비밀번호 변경(`POST /me/password`)은 없습니다 — 인증을 Supabase Auth로 이관하면서 제거됨.

## 식물

### GET `/plants?sort=activity&include_dormant=false`
- 응답: `{items: PlantOut[]}`
- `include_dormant=false`(기본)일 때 `active` + `wilting` 상태만 반환(휴면/보관 제외)

### GET `/plants/{id}` — 단일 식물 (`PlantOut`)
### PATCH `/plants/{id}` — `PlantUpdate` (name, description, species, color)
### DELETE `/plants/{id}?hard=false` — `hard=false`(기본) archive(soft delete) / `hard=true` 완전 삭제

## 봉우리

### GET `/buds?plant_id=&wilting_only=`
- 응답: `{items: BudOut[]}`

### GET `/buds/{id}` — `{bud, history}`
### PATCH `/buds/{id}` — `BudPatch{title?, detail?}` (상태/진행률은 직접 수정 불가)
### PATCH `/buds/{id}/progress` — `BudProgressUpdate{progress, note?}` (0~100 clamp + 자동 상태 전이)
### PATCH `/buds/{id}/move` — `BudMoveRequest{target_plant_id}` (다른 식물로 이동)
### DELETE `/buds/{id}` — 봉우리 삭제 (이력 cascade)

## 통계 / 캘린더

### GET `/stats/summary`
- 응답: `{active_concerns, active_schedules, harvested_this_month, wilting_count, rot_count, total_plants}`
- 매 호출마다 실시간 계산(캐시본을 `garden_state.summary_cache`에 갱신)

### GET `/briefing/today` — 일일 브리핑 문자열 (`{briefing}`). 매 호출 재생성(순수 문자열 포맷, LLM 미사용)

### GET `/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD`
- 응답: `{events: {"YYYY-MM-DD": [{id,title,status,type,detail,plant_name,plant_id,source,...},...]}}`
- from/to 형식 오류 시 400, 366일 초과 시 400
- 봉우리 deadline(`source:"bud"`) + 독립 일정(`source:"event"`, `color` 포함)을 병합
- `detail` 필드에 AI가 저장한 시간·장소 정보 포함

### POST `/calendar/events` — `{title, date, plant_id?, detail?, color?}` 독립 일정 생성
### PATCH `/calendar/events/{id}` — `{title?, date?, plant_id?, detail?, color?}`
### DELETE `/calendar/events/{id}`

## 대화

### GET `/conversations/list`
- 응답: `{conversations: [...]}`
- 메시지가 없는 빈 대화는 제외
- 대화 기록 브라우저(`/history`)에서 사용

### GET `/conversations?scope=global&scope_id=&limit=20`
- 해당 스코프의 메시지 목록 반환
- `{messages: [{id, role, text, at}]}`

### DELETE `/conversations?scope=&scope_id=` — 현재 스코프 대화 영구 삭제(메시지 cascade)

### POST `/conversations/search` — `{query, scope, scope_id, limit}`

## 알림

### GET `/notifications?include_read=false&limit=50`
- `include_read=false`(기본) 안 읽은 알림만 / `include_read=true` 전체 기록(읽음 포함)
- 응답: `{items: [{id, kind, payload, created_at, acked_at}]}`

### POST `/notifications/{id}/ack` — 단일 읽음 처리
### POST `/notifications/ack-all` — 전체 읽음 처리 (`{acked: N}`)

## 채팅 (SSE)

### POST `/chat/message`
- body: `{text, scope: "global|plant|bud|calendar", scope_id?, current_screen?}`
- 응답: `text/event-stream`
- 이벤트 종류:
  - `event: start data: {message_id}`
  - `event: tool_call data: {name, args}`
  - `event: tool_result data: {name, result: {ok, message, data}}`
  - `event: token data: {text}`
  - `event: done data: {}`

## 관리자 (`require_admin`)

`/admin/*` 의 모든 엔드포인트는 admin 역할 전용입니다. 주요 그룹:

- 대시보드·사용자: `GET /admin/stats`, `GET /admin/users`, `GET /admin/users/{id}`,
  `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/settings`
- AI 로그: `GET /admin/logs`, `GET /admin/logs/{filename}` (Supabase `ai_logs` + 파일 미러)
- 알림 발송: `POST /admin/notifications`, `GET /admin/notifications/history`
- 컨트롤러(런타임 설정·SQL·타임 트래블): `GET|PATCH /admin/controller/settings`,
  `POST /admin/controller/settings/reset`, `POST /admin/controller/sql`,
  `POST /admin/controller/scheduler/trigger`, `PATCH /admin/controller/users/{id}/model`,
  `GET /admin/controller/tables`, `GET|PATCH /admin/controller/time`
- 데이터 관리: `GET /admin/data/users/{id}/conversations|plants|buds`,
  `DELETE /admin/data/conversations/{id}`, `.../plants/{id}`, `.../buds/{id}` 등
- 백업/복원: `POST /admin/backup`, `GET /admin/backups`, `.../restore`, `.../download`, `DELETE`

## 기타

### GET `/public/runtime` — 공개 페이지용 표시 안전 런타임 값 (`{llm_default_model, llm_default_model_label}`, 인증 불필요)
### GET `/health` — `{status:"ok"}` (prefix 없음, 인증 불필요)

## 에러 코드

| HTTP | 의미 |
|------|------|
| 400 | 입력 검증 실패 |
| 401 | 인증 필요/실패 |
| 403 | 권한 없음 (관리자 전용 등) |
| 404 | 리소스 없음 또는 다른 사용자 소유 |
| 500 | 서버 내부 오류 |
