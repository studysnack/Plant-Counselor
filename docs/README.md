# Plant Counselor 문서 지도

> 최종 점검: 2026-06-05

문서가 여러 구현 단계를 거치며 함께 남아 있다. 현재 웹 MVP 작업은 아래 우선순위로
읽는다.

1. 실제 코드
2. 루트 [`AGENTS.md`](../AGENTS.md)
3. 루트 [`README.md`](../README.md)
4. [`DEMO_GUIDE.md`](./DEMO_GUIDE.md)
5. 필요한 경우에만 [`구체화.md`](./구체화.md)

루트 `CLAUDE.md`는 더 이상 별도 세션 이력 문서가 아니며 `@AGENTS.md` 포인터만
담는다. 과거 Claude 세션에서 유효한 작업 맥락은 루트 `AGENTS.md`의
`통합된 과거 작업 맥락` 섹션으로 옮겼다.

## 현재 작업용 문서

| 문서 | 용도 |
| --- | --- |
| [`../AGENTS.md`](../AGENTS.md) | 현재 코드 기준 작업 가이드와 운영상 함정 |
| [`../README.md`](../README.md) | 프로젝트 요약, 로컬 실행, 환경변수 |
| [`DEMO_GUIDE.md`](./DEMO_GUIDE.md) | 수동 시연과 회귀 확인 |
| [`구체화.md`](./구체화.md) | 제품 메타포와 초기 UX 의도. 구현 세부는 오래될 수 있다. |
| [`superpowers/specs/2026-05-24-multi-step-orchestrator-design.md`](./superpowers/specs/2026-05-24-multi-step-orchestrator-design.md) | ReAct 오케스트레이터 설계 배경 |

## 역사 자료

| 경로 | 의미 |
| --- | --- |
| [`MVP/`](./MVP/) | 2026-05-27 시점 초기 웹 MVP 스냅샷. 현재 구현 명세로 사용하지 않는다. |
| [`superpowers/plans/`](./superpowers/plans/) | 당시 구현 계획. 완료 후 코드가 바뀐 항목이 있다. |

역사 자료에 SQLAlchemy, SQLite, 쿠키 기반 refresh 인증, 강조색 선택, 14~16개 스킬
설명이 남아 있어도 현재 코드에는 적용하지 않는다.

최신 문서를 갱신할 때는 오래된 설명을 현재 코드로 교체하되, 여전히 유효한 구조,
보안 경계, 운영 주의사항, 확장 체크리스트는 삭제하지 않고 보존한다.
