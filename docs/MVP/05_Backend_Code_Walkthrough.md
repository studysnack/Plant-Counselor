# 05. 백엔드 코드 워크스루

> 모든 백엔드 Python 파일의 **함수·변수·결정 이유**를 빠짐없이 정리한 문서입니다.
> 파일은 의존성 순서대로 정렬되어 있습니다(아래로 갈수록 위 계층에 의존).
>
> **DB 접근은 SQLAlchemy/psycopg2/alembic가 아니라 `supabase-py`(PostgREST HTTP)만 사용합니다.**
> 테이블 스키마는 Supabase 마이그레이션이 관리하며, 백엔드는 service_role 키로 PostgREST REST API를 호출합니다.

---

## 1. `app/config.py`

```python
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://...supabase.co:5432/postgres"  # 런타임 미사용
    supabase_jwt_secret: str = ""
    supabase_url: str = "https://mnqwrofidwotcsvsymnd.supabase.co"
    supabase_service_role_key: str = ""
    llm_api_key: str = ""
    key_encryption_secret: str = "dev-encryption-key-32chars-padded"
    cors_allow_origin: str = "http://localhost:3000"
    class Config:
        env_file = ".env"

settings = Settings()
```

- **역할**: 환경설정 단일 진입점. 모든 다른 모듈은 `from app.config import settings` 만 사용.
- **`supabase_url` / `supabase_service_role_key`**: 실제 DB 접근(`app/db/supa.py`)과 JWKS 검증에 사용. service_role 키는 RLS를 우회.
- **`supabase_jwt_secret`**: JWT HS256 fallback 검증용(Supabase Dashboard의 Legacy JWT Secret).
- **`database_url`**: 기본값만 남아 있고 **런타임에는 사용되지 않음**(psycopg2 직접 연결 폐기). PostgREST HTTP만 사용.
- **`key_encryption_secret`**: Fernet 키 파생용. 32바이트가 아닌 임의 길이여도 `UserService._make_fernet` 에서 SHA-256 후 base64로 안전하게 가공.
- **`cors_allow_origin`**: 단일 origin 또는 콤마 구분 목록. `main._parse_cors_origins` 가 파싱하며 `*`/`null` 은 거부.

## 2. `app/db/supa.py`

```python
@lru_cache(maxsize=1)
def _make_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

def get_client() -> Client:
    return _make_client()

DB = Client   # 시그니처에서 쓰는 타입 별칭
```

- **역할**: Supabase PostgREST 클라이언트 싱글톤. SQLAlchemy `Session` 을 완전히 대체.
- **`@lru_cache(maxsize=1)`**: 클라이언트를 한 번만 생성해 재사용.
- **왜 PostgREST HTTP인가?** Supabase pooler가 `ENOTFOUND`(테넌트 미등록), 직접 연결 호스트는 IPv6 전용이라 psycopg2 직접 연결이 불가능. 대신 HTTPS + service_role 키로 REST API를 호출(RLS 우회).

## 3. DB 스키마 (Supabase가 관리)

ORM 모델 클래스는 없습니다. 테이블은 Supabase 마이그레이션으로 생성되며, 백엔드는
`db.table("...")` 로 접근합니다. 주요 테이블과 의미:

- **`profiles`**: 사용자 프로필. `id`(Supabase Auth `sub`), `email`, `nickname`, `role`(`user`/`admin`),
  `tone`, `ai_model`, `garden_rules`(JSON), `appearance`(JSON), `encrypted_api_key`, `created_at`.
- **`plants`**: `id`(ULID), `user_id`, `name`, `description`, `species`, `color`,
  `status`(`active`/`wilting`/`dormant`/`archived`), `harvested_count`, `rot_count`, `active_bud_count`,
  `last_activity_at`. **`stats` 컬럼은 없음** — `PlantOut` 이 개별 카운터를 `stats` dict로 합성.
- **`buds`**: `id`, `user_id`, `plant_id`, `title`, `detail`, `type`(`concern`/`schedule`),
  `status`, `progress`(0~100), `deadline`, `last_progress_at`, `disappeared_at`, `created_at`, `updated_at`.
  생애주기 상태: `bud → flower → fruit → harvested`, 방치 시 `wilting → rot`(씨앗 `seed` 는 폐기 — 마이그레이션 004).
- **`bud_history`**: 모든 상태 전이 기록(`bud_id`, `from_status`, `to_status`, `at`, `reason`).
- **`conversations`** / **`conversation_messages`**: 대화방(`user_id`, `scope`, `scope_id`) + 메시지(`role`, `text`, `at`, `skill_call`).
- **`garden_state`**: 사용자 1:1 캐시(`summary_cache`, `daily_briefing*`, `last_opened_at`).
- **`notifications`**: `kind`(`bud_wilting`/`bud_rot`/`deadline_warning`/`plant_wilting`/관리자 메시지), `payload`(JSON), `acked_at`.
- **`calendar_events`**: 봉우리와 별개의 독립 일정(`title`, `event_date`, `plant_id`, `detail`, `color`). PostgREST 미노출이라 `exec_admin_query` RPC로 접근.
- **`ai_logs`**: AI 채팅 로그 영구 저장(`filename`, `user_id`, `created_at`, `data` jsonb). 로컬 파일 미러와 병행.

---

## 4. `app/deps.py` (인증 의존성)

```python
def get_db() -> Client:
    from app.db.supa import get_client
    return get_client()

def require_user(authorization, db) -> SimpleNamespace:
    # 1) JWKS(ES256/RS256)로 검증 시도 → 실패 시
    # 2) supabase_jwt_secret(HS256)로 fallback 검증
    #    둘 다 audience="authenticated"
    user_id = payload["sub"]
    user = UserRepository(db).get_by_id(user_id)
    if user is None:  # 프로필 미존재 시 자동 생성(트리거 fallback)
        user = repo.create_profile(user_id, email, nickname)
    return user

def require_admin(user=Depends(require_user)) -> SimpleNamespace:
    if getattr(user, "role", "user") != "admin": raise 403
    return user
```

- **Supabase JWT 검증**: 신규 Supabase 프로젝트는 **ES256(ECDSA P-256)** 으로 서명 → JWKS 엔드포인트(`/auth/v1/.well-known/jwks.json`)에서 EC 공개키를 로드해 검증. `_jwks_cache` 로 1회만 가져옴. HS256 fallback 유지.
- **모든 401 분기를 같은 메시지/헤더(`_CREDS_EXC`)로 통일**: 어느 단계에서 실패했는지 클라이언트가 구분 못 하게.
- **프로필 자동 생성**: DB 트리거(`handle_new_auth_user()`)가 보통 만들지만, 누락 시 `create_profile` fallback.
- **`require_admin`**: `/admin/*` 전체를 보호.

> JWT 발급·갱신은 백엔드가 아니라 **Supabase Auth**가 담당합니다. 따라서 별도 `app/auth/` 패키지나 `app/routers/auth.py`, refresh-token 쿠키 로직은 존재하지 않습니다.

---

## 5. Repositories

모든 repository는 `supabase Client` 를 받아 `db.table(...)` 로 접근하며, dict 결과를
`SimpleNamespace` 로 감싸 반환합니다(`_row` / `_rows` 헬퍼). **`commit`/`refresh` 호출 없음** — PostgREST가 자동 커밋.
빈 결과 처리는 `maybe_single()` 대신 `.limit(1)` + `res.data[0]` 패턴을 사용.

### 5.1 `app/repositories/user_repo.py`

```python
class UserRepository:
    def get_by_id(user_id) -> SimpleNamespace | None     # profiles 테이블
    def create_profile(user_id, email, nickname)
    def update(user_id, fields) -> SimpleNamespace | None
    def delete(user_id) -> None
    def set_encrypted_api_key(user_id, encrypted_key)
    def get_encrypted_api_key(user_id) -> str | None
```

- `profiles` 테이블 직접 접근. 비밀번호 해시는 없음(인증은 Supabase Auth).

### 5.2 `app/repositories/plant_repo.py`

```python
def create(user_id, name, description, species, color) -> Plant   # id=ULID
def get(user_id, plant_id) -> Plant | None   # user_id로 격리
def list(user_id, include_dormant=True, sort="activity", limit=100)
def update(user_id, plant_id, fields) -> Plant | None
```

- 모든 메서드가 `user_id` 를 받음 → 다른 사용자의 식물 접근 차단(수평 권한 격리).
- `list()` 는 항상 `status != "archived"`. `include_dormant=False` 면 `status in ("active","wilting")` 만 — 시든 식물은 정원 뷰에 갈색으로 계속 보임.
- 정렬: `activity` 시 `last_activity_at.desc(nullsfirst=False), created_at.desc()`.

### 5.3 `app/repositories/bud_repo.py`

```python
def create(user_id, plant_id, title, type, detail, deadline) -> Bud
def get(user_id, bud_id) -> Bud | None
def list(user_id, plant_id=None, statuses=None, bud_type=None,
         wilting_only=False, deadline_within_days=None, limit=50)
def update(user_id, bud_id, fields)
def delete(user_id, bud_id) -> bool
def add_history(bud_id, from_status, to_status, reason)
def get_history(bud_id) -> list   # ORDER BY at
```

- `list()` 필터는 모두 optional. `deadline_within_days` 는 `today + N` 이하 cutoff — 캘린더/알림 사전조회용.
- `add_history()` 는 항상 ULID로 새 행 생성.

### 5.4 `app/repositories/conversation_repo.py`

```python
def get_or_create(user_id, scope, scope_id) -> Conversation
def add_message(conversation_id, role, text, skill_call) -> Message
def get_history(user_id, scope, scope_id, limit) -> list   # 최신 N개 후 시간순
def list_conversations_for_user(user_id) -> list[dict]     # /conversations/list 용
def delete_by_scope(user_id, scope, scope_id) -> int
def search(user_id, query, scope, scope_id, limit)
```

- **`get_or_create`** 가 `(user_id, scope, scope_id)` unique 제약과 짝지어 동작.
- **`search`**: `ilike %query%` 단순 검색(LIKE 와일드카드 이스케이프).

### 5.5 `app/repositories/garden_state_repo.py`

```python
def get_or_create(user_id) -> GardenState   # 사용자당 1행
def update(user_id, fields) -> GardenState
```

### 5.6 `app/repositories/notification_repo.py`

```python
def push(user_id, kind, payload) -> Notification
def list_unread(user_id) -> list           # acked_at IS NULL
def list_all(user_id, limit) -> list       # 읽음 포함, 최신순
def ack(user_id, notification_id) -> bool  # acked_at 채움
def ack_all(user_id) -> int
def has_unacked(user_id, kind, ref_id) -> bool   # 중복 deadline 알림 방지
```

### 5.7 `app/repositories/calendar_event_repo.py`

- `calendar_events` 테이블이 PostgREST에 노출되지 않아 **`exec_admin_query` RPC + `_lit()` 이스케이프**로 접근.

---

## 6. Services

서비스 계층도 `commit()/refresh()` 가 없습니다(PostgREST 자동 커밋). 시간 관련 값은 모두 `runtime_settings.now()/today()`(타임 트래블 반영)를 사용.

### 6.1 `app/services/user_service.py`

```python
def _make_fernet() -> Fernet:
    raw = settings.key_encryption_secret.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)

class UserService:
    def get_me(user_id) -> profile
    def update_profile(user_id, fields):
        forbidden = {"id", "email", "created_at"}   # 안전 필드만 통과
    def delete_account(user_id) -> dict:            # bulk cascade 삭제
    def set_api_key(user_id, api_key)               # Fernet 암호화 저장
    def get_api_key(user_id) -> str | None          # 복호화
```

- **`signup`/`authenticate`/`change_password` 없음** — 인증을 Supabase Auth로 이관하며 제거됨.
- **Fernet 키 파생**: 임의 길이 secret을 SHA-256으로 32바이트로 정규화. 같은 secret이면 같은 key → 복호화 보장.
- **`delete_account`**: `buds → plants → conversations → garden_state → notifications` 순으로 user_id 기준 bulk delete(FK CASCADE 활용) + AI 로그 파일 삭제 + **Supabase Auth 사용자 삭제**(admin 키).

### 6.2 `app/services/plant_service.py`

```python
class PlantService:
    def create(user_id, name, description, species, color)
    def get(user_id, plant_id)   # 없으면 ValueError
    def list(user_id, include_dormant=True, sort="activity")
    def update(user_id, plant_id, fields)
    def delete(user_id, plant_id, archive=True):
        if archive: status="archived"   # soft delete
        else: db.table("plants").delete()
    def find_matches(user_id, query, top_k=3)   # ilike name, status != archived
```

- **`find_matches`** 는 `match_plant` 스킬이 호출 — LIKE 와일드카드 이스케이프 후 `ilike "%q%"`.

### 6.3 `app/services/bud_service.py`

```python
_PROGRESS_TRANSITIONS = [(85,"fruit"), (60,"flower")]
_GROWTH_STATUSES = {"bud","flower","fruit","harvested"}
_WILTED_STATUSES = {"wilting","rot"}

class BudService:
    def create(...):  add_history(bud.id, "", "bud", "생성")   # 시작 상태 = bud (seed 폐기)
    def get(user_id, bud_id)   # 없으면 ValueError
    def list(..., wilting_only=False, filters=None)   # filters dict 하위 호환
    def update_status(user_id, bud_id, to_status, reason):
        if to_status == "seed": raise ValueError          # seed 거부
        if 성장상태 and (현재 시듦 or 식물 시듦): raise _NO_REVIVAL_MSG   # 소생 불가
        if to_status == "harvested" and progress < 100: raise   # 수확은 100%만
    def update_progress(user_id, bud_id, progress, auto_transition=True, note=""):
        progress = max(0, min(100, progress))
        if 진행률 상승 and (시듦/식물 시듦): raise   # 소생 불가
        # 85% → fruit, 60% → flower 자동 전이
    def set_deadline / move_to_plant / delete
    def abandon -> update_status("rot")
    def harvest -> update_status("harvested")
    def mark_wilting -> update_status("wilting")
    def get_with_history(user_id, bud_id)
```

**핵심**:
- **`_PROGRESS_TRANSITIONS` 는 내림차순** — 첫 매칭이 가장 진행된 상태(85%↑ → fruit, 그 아래 60%↑ → flower). 더 이상 `(30,"bud")` 단계는 없음.
- **`seed` 폐기**: `update_status` 가 `seed` 를 거부(마이그레이션 004).
- **소생 불가(no-revival)**: 시든/썩은 봉우리(또는 시든 식물에 속한 봉우리)는 성장 상태로 전이하거나 진행률을 올릴 수 없음. 대화는 가능.
- **수확 가드**: `harvested` 는 진행률 100% 봉우리만.
- **`move_to_plant`**: 다른 식물로 이동(보관된 식물로는 이동 불가). 이력에 기록.
- **`abandon/harvest/mark_wilting`** 은 `update_status` 의 의미 있는 별칭.

### 6.4 `app/services/conversation_service.py`

```python
def append(user_id, scope, scope_id, role, text, skill_call=None)
def get_history(user_id, scope, scope_id, limit=20)
def list_conversations(user_id)        # /conversations/list
def delete_conversation(user_id, scope, scope_id)
def search(user_id, query, scope, scope_id, limit=10)
```

- 얇은 래퍼지만 cross-cutting 로직(PII 마스킹, 토큰 카운팅 등)을 끼울 자리.

### 6.5 `app/services/garden_state_service.py`

```python
def refresh_summary(user_id) -> dict:
    # 모든 buds/plants를 가져와 Python에서 카운트(raw SQL 미사용)
    active = {"seed","bud","flower","fruit","wilting"}
    summary = {active_concerns, active_schedules, harvested_this_month,
               wilting_count, rot_count, total_plants}
    _repo.update(user_id, {"summary_cache": summary}); return summary

def get_summary(user_id) -> dict           # 캐시본(summary_cache)
def compute_stats(user_id, scope, plant_id, period) -> dict
def build_briefing(user_id) -> str         # 매 호출 재생성(문자열 포맷)
```

- **Python 집계**: PostgREST에는 `SUM(CASE WHEN)` 같은 임의 집계가 없어, 봉우리 목록을 받아 Python에서 카운트. `active` 집계에 `seed` 를 잠정 포함(마이그레이션 004 전 과거 행 호환).
- **브리핑은 매 호출 재생성** — 하루 캐시 staleness 제거(순수 문자열 포맷, LLM 미사용).

### 6.6 `app/services/transition_service.py`

```python
class TransitionService:
    def scan_all(db):                       # profiles 전체 순회
        for row in profiles: scan_user(db, row["id"], row["garden_rules"])
    def scan_user(db, user_id, garden_rules):
        wilting_days, rot_disappear_days, deadline_warn_days, auto_transition,
        plant_wilt_bud_threshold, plant_wilt_days = rules.get(...) or rs.get(...)
        now, today = rs.now(), rs.today()   # 타임 트래블 반영
        if auto_transition:
            # 1) 활동 정지 N일 → wilting (+ bud_wilting 알림)
            # 2) wilting M일 더 → rot + disappeared_at (+ bud_rot 알림)
            # 3) 식물의 wilting 봉우리 >= N개이고 M일 경과 → 식물 자체 wilting (+ plant_wilting 알림)
        # 4) deadline 임박 봉우리 → deadline_warning (has_unacked로 중복 방지)
```

- **사용자별 규칙**: 각자의 `garden_rules` 우선, 없으면 `runtime_settings` 기본값.
- **`auto_transition` 플래그**: 꺼두면 시듦/썩음 자동 처리 안 함. 단 마감 경고는 항상 발송.
- **식물 단위 시듦(plant-level wilting)**: 봉우리뿐 아니라 식물 전체가 시들 수 있음(`plant_wilt_bud_threshold` / `plant_wilt_days`).

### 6.7 `app/services/calendar_service.py`

- 독립 일정(`calendar_events`) CRUD. `list_range`, `create`, `update`, `delete`. RPC 경로로 접근.

---

## 7. AI 모듈

### 7.1 `app/ai/skill_base.py`

```python
@dataclass
class SkillResult:
    ok: bool; message: str; data: dict = {}; error_code: str = ""

@dataclass
class SkillContext:
    user_id; db
    plant_service, bud_service, garden_state_service, conversation_service, calendar_service = None
    scope: str = "global"   # global | plant | bud | calendar
    scope_id: str | None = None

class SkillBase(ABC):
    name; description; parameters
    def run(self, args, ctx) -> SkillResult: ...
    def to_tool_spec(self) -> dict   # {name, description, input_schema}
```

- 모든 스킬은 name/description/parameters/run만 정의 — 일관성 강제.
- `SkillContext` 에 `scope`/`scope_id` 가 포함되어 세션별 수정·삭제 권한(`app/ai/permissions.py`) 판단.

### 7.2 `app/ai/skill_registry.py`

```python
class SkillRegistry:
    def register(skill)
    def get(name) -> SkillBase | None
    def build_catalog() -> list[dict]    # [skill.to_tool_spec() for ...]
    def dispatch(name, args, ctx) -> SkillResult:
        if skill is None: return SkillResult(ok=False, error_code="not_found")
        try: return skill.run(args, ctx)
        except Exception as e: return SkillResult(ok=False, message=str(e), error_code="internal")
```

- **`dispatch` 가 모든 예외를 캐치** — 단일 스킬 실패가 채팅 전체를 죽이지 않도록.

### 7.3 `app/ai/llm_client.py`

Anthropic IR → Gemini 변환 어댑터(자세한 내용은 `04_AI_Chat_And_Skills.md`).

추가 결정 사항:
- **모델 런타임 교체**: `LLMClient(api_key, model=...)`. 우선순위는 per-user `ai_model` → `runtime_settings.llm_default_model` → `LLMClient.DEFAULT_MODEL`.
- **에러 분류·기록**: Gemini 503(overloaded)/429(rate_limit)/auth/404(model_not_found)/timeout 등을 `_classify_error()` 로 분류해 `error`/`error_kind`/`error_cause` 로 반환 → 관리자 AI 로그에 노출. 503은 지수 백오프 3회 재시도.
- **API 키 미설정**: 친절한 안내 텍스트 반환.

### 7.4 `app/ai/prompt_builder.py`

```python
class PromptBuilder:
    def build_system(ctx, current_screen="홈", stats=None, plants=None,
                     scope="global", scope_id=None, scope_plant_name="",
                     scope_bud_title="", tone="counselor") -> str:
        # 오늘 날짜 = rs.today() (타임 트래블 반영)
        # 톤 가이드(counselor/assistant/friend) + 정원 현황 + 스코프 컨텍스트 + 행동 규칙
```

- **`rs.today()`** 사용 → 타임 트래블 연동. `tone` 으로 응답 말투 선택. 자세한 디자인 의도는 `04_AI_Chat_And_Skills.md` 참고.

### 7.5 `app/ai/chat_orchestrator.py`

```python
MAX_STEPS = 10  # fallback; 실제 값은 runtime_settings.llm_max_steps에서 매 실행 읽음

class ChatOrchestrator:
    def run(user_id, text, scope, scope_id, current_screen, db, tone="counselor"):
        rec = LogRecorder(user_id, text)
        ctx = SkillContext(..., scope=scope, scope_id=scope_id)   # calendar 서비스 포함
        stats = gs_svc.get_summary(...); plants = plant_svc.list(...)
        # scope_plant_name / scope_bud_title 해석 → off-topic 감지에 사용
        system = builder.build_system(..., tone=tone)
        history = 최근 20개 + 새 user 메시지
        yield "event: start"
        for step in range(rs.get("llm_max_steps", MAX_STEPS)):
            result = llm.chat(working_history, catalog, system)
            self._record_llm_error(rec, step+1, result)   # upstream 오류 기록
            if 빈 응답: llm.chat(...) 1회 재시도
            if tool_use:
                yield "event: tool_call"
                skill_result = registry.dispatch(...)
                yield "event: tool_result"
                working_history += [assistant tool_use, user tool_result]
                continue
            break
        if not response_text: result = llm.chat(working_history, [], system)  # 강제 요약
        rec.set_final(response_text)
        for word in response_text.split(): yield "event: token"
        conv_svc.append(..., "assistant", response_text, skill_call=last_tool_use)
        rec.save(db)   # ← db를 넘겨 Supabase ai_logs에 저장
        yield "event: done"
```

**왜 sync generator?** FastAPI `StreamingResponse` 는 sync/async 둘 다 받음. 동기 Gemini SDK·supabase-py 클라이언트를 그대로 쓸 수 있어 간결.

**`error` 이벤트는 없음**: 스킬·LLM 오류는 token/done 흐름 안에서 처리되며, upstream 오류는 `_record_llm_error` 로 로그에만 기록.

**왜 `tool_use_id = name/step`?** Gemini는 function_call에 별도 ID를 안 주므로 우회. 매 라운드에 1개 tool만 호출되므로 안전.

### 7.6 `app/ai/log_recorder.py` + `app/ai/log_store.py`

```python
# log_recorder.LogRecorder — 채팅 한 턴의 전체 컨텍스트를 누적
filename = f"{ts}_{user_id[:8]}.json"
self._data = {timestamp, user_id, user_input, system_prompt, history,
              llm_calls, skill_calls, final_response, events, llm_errors}
def set_system / set_history / log_llm_call / log_llm_result
def log_skill / log_llm_error / log_event / set_final
def save(db=None):  log_store.save(db, filename, user_id, created_at, data)
```

```python
# log_store — Supabase ai_logs 테이블 + 로컬 파일 미러
def save(db, filename, user_id, created_at, data)  # DB 우선(durable), 파일은 미러
def list_rows(db)        # DB + 파일을 filename 기준 dedup 병합(DB 우선)
def get(db, filename)    # 단일 로그 data
def parse_meta(data, filename)   # 목록용 경량 메타(토큰 추정, error_count 등)
def delete_for_user(db, user_id) / delete_all(db)
```

- **왜 DB 미러?** Render 무료처럼 디스크가 휘발성인 환경에서 파일만 쓰면 재시작 시 사라짐. `ai_logs` 테이블이 정본, 파일은 로컬 개발용 best-effort 미러.
- `list_rows` 가 둘을 병합 → DB만/파일만/둘 다 어떤 상황에서도 로그가 보임.
- 관리자 라우터(`admin.py`)가 이 모듈을 통해서만 읽기/삭제.

### 7.7 `app/ai/skills/*.py` (20개 스킬)

`chat.py` `_build_registry()` 에 등록되는 20개 스킬:

| 파일 | 역할 한 줄 |
|------|------------|
| `think.py` | 멀티스텝 계획을 명시화(DB 변경 없음). |
| `match_plant.py` | `PlantService.find_matches(query)` — 중복 방지. |
| `create_plant.py` | `PlantService.create(...)` — 새 분야. |
| `delete_plant.py` | `PlantService.delete(archive=...)`. |
| `create_bud.py` | `BudService.create(...)` — 봉우리 추가. |
| `update_bud_status.py` | `BudService.update_status(...)` (seed 거부·소생 불가 가드). |
| `update_bud_progress.py` | `BudService.update_progress(...)` (85→fruit, 60→flower). |
| `set_deadline.py` | `BudService.set_deadline(...)` (ISO 파싱 실패 시 invalid_argument). |
| `abandon_bud.py` | `BudService.abandon(...)` → rot. |
| `harvest_bud.py` | `BudService.harvest(...)` (100%만). |
| `list_plants.py` | `PlantService.list(...)`. |
| `list_buds.py` | `BudService.list(...)`. |
| `get_statistics.py` | `GardenStateService.compute_stats(...)`. |
| `get_garden_briefing.py` | `GardenStateService.build_briefing()`. |
| `search_conversation.py` | `ConversationService.search(...)`. |
| `suggest_scope_change.py` | 스코프 불일치 감지 후 세션 변경 제안. |
| `create_calendar_event.py` | 독립 일정 생성. |
| `list_calendar_events.py` | 독립 일정 조회. |
| `update_calendar_event.py` | 독립 일정 수정(권한: calendar 스코프). |
| `delete_calendar_event.py` | 독립 일정 삭제. |

각 스킬의 description은 **LLM에 대한 가이드**입니다(예: `create_plant` 은 "match_plant로 중복 확인" 프로토콜 강제).

### 7.8 `app/ai/permissions.py`

- 세션 스코프별 수정·삭제 권한(`can_modify_bud`/`can_delete_plant`/`can_modify_calendar_event`/`guard_bud`). 변이 스킬이 권한 밖이면 forbidden 거부.

---

## 8. Routers

### 8.1 `app/main.py`

```python
@asynccontextmanager
async def lifespan(app):
    sched = setup_scheduler(); yield; sched.shutdown()
    # Base.metadata.create_all 없음 — 테이블은 Supabase 마이그레이션이 관리

api = FastAPI(title="Plant Counselor API", version="0.2.0", lifespan=lifespan)

def _parse_cors_origins(raw):   # 콤마 구분, '*'/'null' 거부, scheme/netloc 검증

PREFIX = "/api/v1"
for r in [me, plants, buds, stats, chat, conversations, notifications, public, admin]:
    api.include_router(r.router, prefix=PREFIX)

@api.get("/health")
def health(): return {"status":"ok"}

# 전체 앱을 CORSMiddleware로 감싸 500 응답에도 CORS 헤더가 붙도록
app = CORSMiddleware(app=api, allow_origins=_cors_origins, allow_credentials=True, ...)
```

- **`Base.metadata.create_all` 없음**: 스키마는 Supabase 마이그레이션이 관리(SQLAlchemy 미사용).
- **`auth` 라우터 없음**: 인증은 Supabase Auth.
- **CORS가 앱 전체를 래핑**: 미처리 500 응답도 CORS 헤더를 포함해, 브라우저가 진짜 서버 오류 대신 오해의 소지가 있는 CORS 실패를 보고하지 않게.
- **`/health`**: prefix 없이 200(인증 불필요).

### 8.2 `app/routers/me.py`

- `GET /me` — 현재 프로필(`UserOut`).
- `PATCH /me` — `UserUpdate`(nickname/tone/ai_model/garden_rules/appearance).
- `DELETE /me` — 회원탈퇴(`UserService.delete_account`).
- `PUT /me/api-key` — Fernet 암호화 저장.
- (비밀번호 변경 엔드포인트 없음.)

### 8.3 `app/routers/plants.py`

```python
@router.get("")        # list (sort, include_dormant)
@router.get("/{id}")   # detail
@router.patch("/{id}") # PlantUpdate
@router.delete("/{id}?hard=bool")  # archive(기본) 또는 hard delete
```

### 8.4 `app/routers/buds.py`

```python
@router.get("")              # 필터: plant_id, wilting_only
@router.get("/{id}")         # {bud, history}
@router.patch("/{id}")       # BudPatch{title?, detail?}
@router.patch("/{id}/move")  # BudMoveRequest{target_plant_id} → move_to_plant
@router.delete("/{id}")      # 봉우리 삭제
@router.patch("/{id}/progress")  # BudProgressUpdate{progress, note?} (자동 전이)
```

- `PATCH /{id}` 는 제목/detail만 직접 수정. 상태는 진행률 슬라이더(`/progress`)·이동·삭제·채팅 스킬로만 변경.

### 8.5 `app/routers/stats.py`

```python
GET /stats/summary    -> refresh_summary 실시간 계산
GET /briefing/today   -> build_briefing (매 호출 재생성)
GET /calendar?from=&to=  -> 봉우리 deadline + 독립 일정 병합, from/to ISO 검증, 최대 366일
# 독립 일정 CRUD
POST  /calendar/events
PATCH /calendar/events/{id}
DELETE /calendar/events/{id}
```

### 8.6 `app/routers/conversations.py`

```python
GET    /conversations/list             # 대화방 요약 목록
GET    /conversations?scope=&scope_id=&limit=   # 메시지 목록
DELETE /conversations?scope=&scope_id=          # 스코프 대화 삭제
POST   /conversations/search { query, scope, scope_id, limit }
```

### 8.7 `app/routers/notifications.py`

```python
GET  /notifications?include_read=&limit=   # 안 읽음(기본) 또는 전체
POST /notifications/{id}/ack
POST /notifications/ack-all
```

### 8.8 `app/routers/chat.py`

```python
_REGISTRY = _build_registry()   # 모듈 로드 시 1회, 20개 스킬 등록
_PROMPT_BUILDER = PromptBuilder()

def _resolve_api_key(db, user):
    return UserService(db).get_api_key(user.id) or settings.llm_api_key

@router.post("/chat/message")
def chat_message(req, user, db):
    model = getattr(user, "ai_model", None) or rs.get("llm_default_model", LLMClient.DEFAULT_MODEL)
    llm = LLMClient(api_key, model=model)
    services = {plant, bud, garden_state, conversation, calendar}
    orchestrator = ChatOrchestrator(llm, _REGISTRY, _PROMPT_BUILDER, services)
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})
```

- **registry/prompt_builder는 모듈 캐시**(stateless). **services/llm은 매 요청**(DB 클라이언트는 공유 싱글톤이지만 사용자 API 키·모델이 매번 다름).
- **모델 우선순위**: per-user `ai_model` → runtime `llm_default_model` → `LLMClient.DEFAULT_MODEL`.
- **`X-Accel-Buffering: no`**: reverse proxy가 SSE를 버퍼링하지 않도록.

### 8.9 `app/routers/admin.py` (`require_admin`)

`/admin/*` 전체가 관리자 전용. 대시보드 통계, 사용자/역할 관리, AI 로그 브라우저(log_store 경유),
알림 발송, 런타임 컨트롤러(설정·SQL 실행기·타임 트래블·스케줄러 트리거), 데이터 관리(개별 삭제),
백업/복원 엔드포인트를 제공. (전체 목록은 `06_API_Reference.md` 참고.)

### 8.10 `app/routers/public.py`

- `GET /public/runtime` — 인증 없이 표시 안전한 런타임 값(기본 모델 ID·라벨)만 노출.

## 9. `app/scheduler/jobs.py`

```python
scheduler = BackgroundScheduler()

def setup_scheduler():
    interval = rs.get("scheduler_interval_minutes", 10)
    @scheduler.scheduled_job("interval", minutes=interval, id="transition_scan")
    def transition_scan():
        db = get_client()
        TransitionService().scan_all(db)
    scheduler.start(); return scheduler
```

- **간격은 `runtime_settings`** 에서 읽음(기본 10분). `get_client()` 싱글톤을 그대로 사용.
- **`id="transition_scan"`**: 중복 등록 방지.

---

## 10. `app/runtime_settings.py`

인메모리 런타임 설정 저장소(`DEFAULTS` + `_store`). JSON 스냅샷으로 재시작 후에도 유지 가능.

```python
DEFAULTS = {
    "llm_default_model": "gemini-2.5-flash", "llm_max_steps": 10, "llm_temperature": None,
    "scheduler_interval_minutes": 10,
    "default_wilting_days": 7, "default_rot_disappear_days": 14,
    "default_deadline_warn_days": 3, "default_auto_transition": True,
    "default_plant_wilt_bud_threshold": 2, "default_plant_wilt_days": 3,
    "system_log_level": "INFO", "system_max_log_files": 500,
    "app_timezone_offset_hours": 9,   # KST
    "time_offset_seconds": 0,         # 타임 트래블
}
AVAILABLE_MODELS = [ ... ]   # 관리자 모델 드롭다운(기본+per-user)이 공유하는 단일 출처

def get/get_all/set/set_many/reset/reset_all
def save_snapshot/load_snapshot   # JSON 스냅샷
def real_now()   # KST wall-clock (타임 트래블 미반영)
def now()        # real_now() + time_offset_seconds
def today()      # now().date()
```

- **타임 트래블**: `now() = (utcnow + tz_offset) + time_offset_seconds`. transition_service·prompt_builder가 `now()/today()` 사용.
- **`app_timezone_offset_hours=9`**: 모든 사용자 대상 날짜를 KST로 계산해 프론트(KST)와 "오늘" 일치.

---

## 11. `app/schemas/*` (Pydantic v2)

ORM이 없으므로 모든 Out 스키마는 `ConfigDict(from_attributes=True)` 로 `SimpleNamespace`/dict에서 변환합니다.

### `schemas/user.py`
- `UserOut`(email/nickname/role/tone/ai_model/garden_rules/appearance/created_at, `model_validator`로 NULL → 기본값 coerce), `UserUpdate`(optional), `ApiKeySet{api_key}`.

### `schemas/plant.py`
- `PlantOut` — `model_validator(mode="before")` 로 `harvested_count`/`rot_count`/`active_bud_count` 컬럼을 `stats` dict로 합성(DB에 `stats` 컬럼 없음).
- `PlantUpdate` — PATCH용 optional 4개(name/description/species/color).

### `schemas/bud.py`
- `BudOut`, `BudHistoryOut`, `BudPatch{title?, detail?}`, `BudProgressUpdate{progress, note?}`, `BudMoveRequest{target_plant_id}`.
- `BudPatch` 가 status/progress/deadline을 받지 않는 이유: 그것들은 전용 엔드포인트·스킬로만 변경.

### `schemas/conversation.py`
- `ChatRequest{text, scope="global", scope_id?, current_screen="홈"}`.

---

## 12. 마이그레이션 (`backend/migrations/`)

Supabase에 적용하는 SQL 마이그레이션:

- `001_calendar_events.sql` — 독립 일정 테이블.
- `002_ai_logs.sql` — AI 로그 영구 저장 테이블.
- `003_calendar_event_color.sql` — 일정 색상 컬럼.
- `004_remove_seed_bud_status.sql` — `seed` 상태 제거(과거 행 → `bud` 승격).

> Alembic은 사용하지 않습니다. 스키마 변경은 Supabase 마이그레이션 SQL 또는 컨트롤러 SQL 실행기로 적용합니다.

## 13. `backend/run.py`

```python
import uvicorn
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True,
                reload_excludes=["*.json", "logs/**"])
```

- **`reload_excludes`**: 런타임 설정 스냅샷(`*.json`)·채팅 로그(`logs/**`) 저장 시 서버 재로드 방지.
- prod에선 `uvicorn app.main:app --workers 4` 등으로 직접 실행 권장.

---

## 14. 결정 요약 표

| 결정 | 대안 | 채택 이유 |
|------|------|-----------|
| supabase-py PostgREST HTTP | SQLAlchemy/psycopg2 | pooler ENOTFOUND·IPv6 전용 직접 연결 회피 |
| Supabase Auth(Google OAuth) | 자체 JWT 인증 | 소셜 로그인 UX, 인증 구현 제거 |
| ES256 JWKS 검증(HS256 fallback) | HS256 단독 | 신규 Supabase 프로젝트는 ES256 서명 |
| ULID id | UUID4 / auto-increment | 정렬 가능 + URL safe + 디버깅 친화 |
| Fernet + SHA-256 파생 | 별도 KMS | 단일 배포 환경에서 충분 |
| ai_logs DB + 파일 미러 | 파일 단독 | 휘발성 디스크(Render)에서도 로그 보존 |
| runtime_settings 인메모리 + 스냅샷 | 환경변수만 | 무중단 런타임 변경 + 타임 트래블 |
| ReAct 루프 자체 구현 | LangChain | 외부 의존 최소화, Gemini SDK 직접 매핑 |
| Anthropic 형식 IR | Gemini 직접 형식 | 향후 멀티-LLM 어댑터 용이 |
| sync generator SSE | async/EventSource | 동기 SDK·클라이언트와 자연스러움 |
| CORSMiddleware로 앱 전체 래핑 | add_middleware | 500 응답에도 CORS 헤더 보장 |
