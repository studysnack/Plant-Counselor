# 08. Operations

## 1. 개발 환경 실행

### 백엔드
```bash
cd backend
poetry config virtualenvs.in-project true --local
poetry install
# backend/.env 직접 생성 후 환경 변수 입력 (아래 표 참고)
poetry run python run.py            # 또는: poetry run uvicorn app.main:app
```
- 기본 포트 8000, hot reload ON.
- 헬스체크: `curl http://localhost:8000/api/v1/health`
- DB는 Supabase PostgREST HTTP(`supabase-py`)로 접근하므로 로컬 DB 설치는 불필요.

### 프론트엔드
```bash
cd frontend
npm install
npm run dev                         # Next.js 16
```
- 기본 포트 3000 (점유 시 3001로 fallback).
- `.env.local` 의 `NEXT_PUBLIC_API_BASE` 는 기본 `http://localhost:8000/api/v1`,
  `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` 도 설정.

## 2. 환경 변수

`backend/.env` (pydantic-settings, `app/config.py`):

| 키 | 기본값 | 비고 |
|----|--------|------|
| `SUPABASE_URL` | `https://mnqwrofidwotcsvsymnd.supabase.co` | Supabase 프로젝트 URL |
| `SUPABASE_JWT_SECRET` | `""` | Supabase Dashboard → Settings → API → JWT Secret (Legacy). JWT 검증용 |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | PostgREST 접근(서비스 롤, RLS 우회). **노출 금지** |
| `LLM_API_KEY` | `""` | 사용자별 키가 없을 때만 fallback. **개발 외엔 비워두는 게 안전** |
| `KEY_ENCRYPTION_SECRET` | `dev-encryption-key-32chars-padded` | API 키 암호화(Fernet). **prod에서 교체 + 안전한 곳에 보관** |
| `CORS_ALLOW_ORIGIN` | `http://localhost:3000` | prod 도메인. 콤마로 여러 origin 허용 가능 |

> `DATABASE_URL` 키는 `config.py` 에 남아 있지만 일반 CRUD 런타임에는 사용되지 않습니다
> (실제 DB 접근은 `supabase-py` PostgREST HTTP). 인증은 Supabase Auth(Google OAuth) +
> ES256 JWKS 검증(HS256 fallback)이며, 자체 JWT 발급/refresh 토큰은 사용하지 않습니다.

## 3. 마이그레이션

- 스키마는 Supabase에서 관리합니다. alembic/`create_all` 은 사용하지 않습니다.
- 변경용 SQL은 `backend/migrations/*.sql` 에 보관하며, Supabase Dashboard 또는
  `/admin/controller` → SQL 실행기에 1회 붙여넣어 적용합니다.
  - `001_calendar_events.sql` — 독립 일정 테이블
  - `002_ai_logs.sql` — AI 채팅 로그 영구 저장 테이블(`ai_logs`)
  - `003_calendar_event_color.sql` — 일정 색상 컬럼
  - `004_remove_seed_bud_status.sql` — `seed` 상태 제거, 봉우리 기본값 `bud`
  - `005_calendar_event_time.sql` — 독립 일정 시간(`event_time`)·종일(`all_day`) 컬럼
  - `006_calendar_event_end_repeat.sql` — 독립 일정 종료일시(`end_date`/`end_time`)·반복(`repeat_rule`) 컬럼

## 4. 로그

- AI 채팅 로그: `app/ai/log_store.py`가 저장/조회/삭제를 담당.
  - **저장**: Supabase `ai_logs` 테이블(정본) + `backend/logs/chat/*.json` 로컬 미러. 디스크가 휘발성인 호스트(Render 무료 등)에서도 재시작 후 로그가 살아남게 하기 위함.
  - **조회**(`list_rows`): DB 행 + 로컬 파일을 **filename 기준으로 병합·중복 제거(DB 우선)**. DB만/파일만/둘 다 어느 경우든 표시됨. 관리자 AI 로그 페이지·대시보드가 이 결과를 사용.
  - **테이블 생성**: `backend/migrations/002_ai_logs.sql`을 Supabase에 1회 실행(미실행 시 파일 폴백으로 동작).
  - ⚠ 이전 구현은 DB 조회 결과가 비어 있을 때 파일로 폴백하지 않아, 테이블이 비어 있으면 기존 파일 로그가 "로그 없음"으로 가려지던 버그가 있었음 → 병합 방식으로 수정.
- 표준 로그: stdout. uvicorn 기본 포맷.

## 5. 백업

- 데이터는 Supabase에 있으므로 SQLite 파일 복사/`pg_dump` 는 해당 없음.
- 앱 내장 백업: `/admin/data` 페이지(또는 `POST /admin/backup`)가 전체 테이블을
  타임스탬프 ZIP(`meta.json` + `data.json`)으로 덤프합니다(`app/services/backup_service.py`).
  복원 시 동일 PK 행은 건너뛰며(덮어쓰기 방지) FK 순서로 복원합니다.
  백업 파일은 `backend/backups/` 에 저장 — **휘발성 디스크 호스트(Render 무료 등)에서는
  생성 후 즉시 다운로드**해 두어야 재시작 시 사라지지 않습니다.
- Supabase 자체 백업(관리형 PostgreSQL의 PITR/스냅샷)도 별도로 활용할 수 있습니다.

## 6. 배포 & 운영 체크리스트 (prod 전환 시)

배포 구성: 프론트엔드 = **Vercel**, 백엔드 = **Render**(`render.yaml` Blueprint),
DB/Auth = **Supabase**. 자세한 내용은 `docs/DEPLOYMENT_GUIDE.md` 참고.

- Render 백엔드: `render.yaml` 의 `startCommand` 는
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /health`.
  환경 변수(`SUPABASE_*`, `LLM_API_KEY`, `KEY_ENCRYPTION_SECRET`, `CORS_ALLOW_ORIGIN`)는
  Render 대시보드 Environment 탭에서 입력(`sync: false`).

1. `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `KEY_ENCRYPTION_SECRET` 안전하게 보관.
2. `CORS_ALLOW_ORIGIN` 을 실제 Vercel 도메인으로 고정(콤마로 여러 origin 가능).
3. Supabase Google OAuth 리다이렉트 URI에 prod 도메인 추가.
4. APScheduler가 multi-worker/다중 인스턴스에서 중복 실행되지 않도록 단일 인스턴스 가정 유지.
5. **Render 무료 플랜 주의**: 콜드 스타트(유휴 시 슬립) + 휘발성 디스크 →
   `backend/logs/chat/` 가 재시작 시 삭제됨. AI 로그가 Supabase `ai_logs` 테이블에
   저장되는 이유(섹션 4). `002_ai_logs.sql` 적용 필수.
6. AI 로그 보존 정책(예: 오래된 `ai_logs` 행 정리) 추가.
7. Gemini API 사용량 모니터링 및 quota 조정.

## 7. 자주 보는 명령

```bash
# 로컬 채팅 로그 미러를 최근 순으로 보기 (정본은 Supabase ai_logs 테이블)
ls -t backend/logs/chat | head
# 관리자 AI 로그 페이지(/admin/logs)는 DB+파일을 병합해 표시

# 프론트 타입체크
cd frontend && npx tsc --noEmit

# 백엔드 모든 .py 구문 OK 확인
cd backend && python -c "import ast,glob; [ast.parse(open(f,encoding='utf-8').read()) for f in glob.glob('app/**/*.py',recursive=True)]; print('OK')"
```
