from __future__ import annotations
from app.ai.skill_base import SkillBase, SkillResult, SkillContext


class CreateCalendarEventSkill(SkillBase):
    name = "create_calendar_event"
    description = (
        "캘린더에 단순 일정을 추가합니다. 봉우리(성장·진행률 추적)를 만들지 않고, "
        "약속·예약·리마인더처럼 진행 관리가 필요 없는 순수 일정에 사용합니다. "
        "어떤 식물(분야)과 관련된 일정인지 plant_id로 연결할 수 있습니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "일정 제목"},
            "date": {"type": "string", "description": "시작 날짜 (YYYY-MM-DD)"},
            "time": {"type": "string", "description": "시작 시간 (HH:MM, 하루 종일이면 생략)"},
            "end_date": {"type": "string", "description": "종료 날짜 (YYYY-MM-DD, 선택, 기본 시작 날짜)"},
            "end_time": {"type": "string", "description": "종료 시간 (HH:MM, 하루 종일이면 생략)"},
            "all_day": {"type": "boolean", "description": "하루 종일 일정 여부 (기본 true)"},
            "repeat_rule": {
                "type": "string",
                "enum": ["none", "daily", "weekly", "monthly", "yearly"],
                "description": "반복 규칙 (선택, 기본 none)",
            },
            "plant_id": {"type": "string", "description": "관련 식물 ID (선택)"},
            "detail": {"type": "string", "description": "장소 등 세부 정보 (선택)"},
            "color": {
                "type": "string",
                "enum": ["olive", "blue", "yellow", "red", "pink", "purple"],
                "description": "일정 표시 색상 (선택, 기본 olive)",
            },
        },
        "required": ["title", "date"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        from datetime import date

        try:
            event_date = date.fromisoformat(str(args["date"])[:10])
            end_date = date.fromisoformat(str(args["end_date"])[:10]) if args.get("end_date") else None
        except (ValueError, KeyError, TypeError):
            return SkillResult(
                ok=False,
                message="날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)",
                error_code="bad_date",
            )

        if ctx.calendar_service is None:
            return SkillResult(ok=False, message="캘린더 서비스를 사용할 수 없습니다.", error_code="no_service")

        try:
            ev = ctx.calendar_service.create(
                ctx.user_id,
                args.get("plant_id"),
                args["title"],
                args.get("detail", ""),
                event_date,
                args.get("time"),
                end_date,
                args.get("end_time"),
                bool(args.get("all_day", True)),
                args.get("repeat_rule", "none"),
                args.get("color", "olive"),
            )
        except ValueError as e:
            return SkillResult(ok=False, message=str(e), error_code="bad_time")
        time_label = "하루 종일" if getattr(ev, "all_day", True) else (
            f"{str(getattr(ev, 'event_time', ''))[:5]}~{str(getattr(ev, 'end_time', ''))[:5]}"
        )
        return SkillResult(
            ok=True,
            message=f"일정 '{ev.title}'을(를) {event_date.isoformat()} {time_label}에 추가했습니다.",
            data={"event_id": ev.id, "repeat_rule": getattr(ev, "repeat_rule", "none")},
        )
