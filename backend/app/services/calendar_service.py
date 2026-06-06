"""CalendarService — standalone calendar events (plain schedules, not buds)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from supabase import Client

from app.calendar_colors import DEFAULT_CALENDAR_EVENT_COLOR, validate_calendar_event_color
from app.repositories.calendar_event_repo import CalendarEventRepository

REPEAT_RULES = {"none", "daily", "weekly", "monthly", "yearly"}


class CalendarService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self._repo = CalendarEventRepository(db)

    @staticmethod
    def normalize_time(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        parts = text.split(":")
        if len(parts) < 2:
            raise ValueError("시간 형식이 올바르지 않습니다. (HH:MM)")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            raise ValueError("시간 형식이 올바르지 않습니다. (HH:MM)")
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("시간 형식이 올바르지 않습니다. (HH:MM)")
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def normalize_repeat_rule(value: str | None) -> str:
        rule = (value or "none").strip().lower()
        if rule not in REPEAT_RULES:
            raise ValueError("반복 값이 올바르지 않습니다.")
        return rule

    @staticmethod
    def _validate_range(event_date: date, event_time: str | None, end_date: date,
                        end_time: str | None, all_day: bool) -> None:
        if end_date < event_date:
            raise ValueError("종료 날짜는 시작 날짜보다 빠를 수 없습니다.")
        if all_day:
            return
        if event_time is None or end_time is None:
            raise ValueError("시간을 선택하거나 하루 종일 일정을 켜주세요.")
        if end_date == event_date and end_time <= event_time:
            raise ValueError("종료 시간은 시작 시간보다 뒤여야 합니다.")

    def create(self, user_id: str, plant_id: str | None, title: str,
               detail: str, event_date: date, event_time: str | None = None,
               end_date: date | None = None, end_time: str | None = None,
               all_day: bool = True, repeat_rule: str = "none",
               color: str = DEFAULT_CALENDAR_EVENT_COLOR) -> SimpleNamespace:
        normalized_time = None if all_day else self.normalize_time(event_time)
        normalized_end_time = None if all_day else self.normalize_time(end_time)
        normalized_end_date = end_date or event_date
        self._validate_range(event_date, normalized_time, normalized_end_date, normalized_end_time, all_day)
        return self._repo.create(
            user_id, plant_id, title, detail, event_date, normalized_time,
            normalized_end_date, normalized_end_time, all_day,
            self.normalize_repeat_rule(repeat_rule),
            validate_calendar_event_color(color),
        )

    def list_range(self, user_id: str, d_from: date, d_to: date) -> list[SimpleNamespace]:
        return self._repo.list_range(user_id, d_from, d_to)

    def update(self, user_id: str, event_id: str, fields: dict) -> SimpleNamespace:
        if "color" in fields:
            fields["color"] = validate_calendar_event_color(fields["color"])
        if "repeat_rule" in fields:
            fields["repeat_rule"] = self.normalize_repeat_rule(fields["repeat_rule"])
        if fields.get("all_day") is True:
            fields["event_time"] = None
            fields["end_time"] = None
        elif fields.get("all_day") is False:
            fields["event_time"] = self.normalize_time(fields.get("event_time"))
            fields["end_time"] = self.normalize_time(fields.get("end_time"))
            if fields["event_time"] is None:
                raise ValueError("시간을 선택하거나 하루 종일 일정을 켜주세요.")
            if fields["end_time"] is None:
                raise ValueError("종료 시간을 선택하거나 하루 종일 일정을 켜주세요.")
        elif "event_time" in fields:
            fields["event_time"] = self.normalize_time(fields.get("event_time"))
            if fields["event_time"] is None:
                fields["all_day"] = True
                fields["end_time"] = None
            else:
                fields["all_day"] = False
        if "end_time" in fields and fields.get("all_day") is not True:
            fields["end_time"] = self.normalize_time(fields.get("end_time"))

        current = self._repo.get(user_id, event_id)
        if current is None:
            raise ValueError(f"일정을 찾을 수 없습니다: {event_id}")

        event_date = fields.get("event_date") or date.fromisoformat(str(current.event_date)[:10])
        end_date = fields.get("end_date") or date.fromisoformat(str(getattr(current, "end_date", current.event_date))[:10])
        all_day = fields.get("all_day") if "all_day" in fields else bool(getattr(current, "all_day", True))
        event_time = fields.get("event_time") if "event_time" in fields else (
            str(getattr(current, "event_time", ""))[:5] if getattr(current, "event_time", None) else None
        )
        end_time = fields.get("end_time") if "end_time" in fields else (
            str(getattr(current, "end_time", ""))[:5] if getattr(current, "end_time", None) else None
        )
        self._validate_range(event_date, event_time, end_date, end_time, all_day)

        ev = self._repo.update(user_id, event_id, fields)
        if ev is None:
            raise ValueError(f"일정을 찾을 수 없습니다: {event_id}")
        return ev

    def delete(self, user_id: str, event_id: str) -> bool:
        return self._repo.delete(user_id, event_id)
