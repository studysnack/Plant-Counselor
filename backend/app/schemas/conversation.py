from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    text: str
    scope: str = "global"
    scope_id: str | None = None
    current_screen: str = "홈"
    # Default OFF: the AI executes intents immediately (the app's core design —
    # "의도가 충분하면 확인 질문 없이 즉시 실행"). Confirmation is opt-in: a client
    # may send require_confirmation=true to get a confirmation_required event first.
    require_confirmation: bool = False
    confirmed_actions: list[dict] | None = None
