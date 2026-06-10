from __future__ import annotations
from app.ai.calendar_event_args import normalize_update_time_fields
from app.ai.permissions import can_modify_calendar_event
from app.ai.skill_base import SkillBase, SkillResult, SkillContext


class UpdateCalendarEventSkill(SkillBase):
    name = "update_calendar_event"
    description = (
        "캘린더의 '일반 일정'(봉우리가 아닌 순수 일정)을 수정합니다. "
        "event_id가 필요하므로 먼저 list_calendar_events로 대상을 찾으세요. "
        "캘린더 세션 또는 전체 세션에서만 사용할 수 있습니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "수정할 일정 ID"},
            "title": {"type": "string", "description": "새 제목 (선택)"},
            "date": {"type": "string", "description": "새 시작 날짜 YYYY-MM-DD (선택)"},
            "time": {"type": "string", "description": "새 시작 시간 HH:MM (선택, 지정하면 all_day=false로 처리)"},
            "end_date": {"type": "string", "description": "새 종료 날짜 YYYY-MM-DD (선택)"},
            "end_time": {"type": "string", "description": "새 종료 시간 HH:MM (선택, 시작 시간만 바꾸면 1시간 뒤로 자동 보정)"},
            "all_day": {"type": "boolean", "description": "하루 종일 일정 여부 (선택)"},
            "repeat_rule": {
                "type": "string",
                "enum": ["none", "daily", "weekly", "monthly", "yearly"],
                "description": "새 반복 규칙 (선택)",
            },
            "detail": {"type": "string", "description": "새 세부 정보 (선택)"},
            "plant_id": {"type": "string", "description": "연결할 식물 ID (선택)"},
            "color": {
                "type": "string",
                "enum": ["olive", "blue", "yellow", "red", "pink", "purple"],
                "description": "새 표시 색상 (선택). 한국어 요청은 올리브/초록=olive, 파랑=blue, 노랑=yellow, 빨강=red, 분홍=핑크=pink, 보라=purple로 매핑",
            },
        },
        "required": ["event_id"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        allowed, msg = can_modify_calendar_event(ctx)
        if not allowed:
            return SkillResult(ok=False, message=msg, error_code="forbidden", data={"forbidden": True})
        if ctx.calendar_service is None:
            return SkillResult(ok=False, message="캘린더 서비스를 사용할 수 없습니다.", error_code="no_service")

        fields: dict = {}
        if args.get("title") is not None:
            fields["title"] = args["title"]
        if args.get("detail") is not None:
            fields["detail"] = args["detail"]
        if args.get("plant_id") is not None:
            fields["plant_id"] = args["plant_id"]
        if args.get("color") is not None:
            fields["color"] = args["color"]
        if args.get("all_day") is not None:
            fields["all_day"] = bool(args["all_day"])
        if "time" in args:
            fields["event_time"] = args.get("time")
        if "end_time" in args:
            fields["end_time"] = args.get("end_time")
        if args.get("repeat_rule") is not None:
            fields["repeat_rule"] = args["repeat_rule"]
        if args.get("date") is not None:
            from datetime import date
            try:
                fields["event_date"] = date.fromisoformat(str(args["date"])[:10])
            except (ValueError, TypeError):
                return SkillResult(ok=False, message="날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)", error_code="bad_date")
        if args.get("end_date") is not None:
            from datetime import date
            try:
                fields["end_date"] = date.fromisoformat(str(args["end_date"])[:10])
            except (ValueError, TypeError):
                return SkillResult(ok=False, message="종료 날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)", error_code="bad_date")
        if not fields:
            return SkillResult(ok=False, message="수정할 내용이 없습니다.", error_code="no_fields")

        try:
            current = ctx.calendar_service._repo.get(ctx.user_id, args["event_id"])
            if current is None:
                return SkillResult(ok=False, message="일정을 찾을 수 없습니다.", error_code="not_found")
            start, end, event_time, end_time, all_day = normalize_update_time_fields(fields, current)
            repeat_rule = fields.get("repeat_rule") or getattr(current, "repeat_rule", "none") or "none"
            conflicts = ctx.calendar_service.detect_conflicts(
                ctx.user_id, start, event_time, end, end_time, all_day, repeat_rule,
                exclude_event_id=args["event_id"],
            )
            ev = ctx.calendar_service.update(ctx.user_id, args["event_id"], fields)
        except ValueError as e:
            message = str(e)
            code = "not_found" if "찾을 수 없습니다" in message else "bad_time"
            return SkillResult(ok=False, message=message, error_code=code)
        return SkillResult(
            ok=True,
            message=(
                f"일정 '{ev.title}'을(를) 수정했습니다."
                + (f" 겹치는 일정 {len(conflicts)}개가 있습니다." if conflicts else "")
            ),
            data={"event_id": ev.id, "conflicts": conflicts},
        )
