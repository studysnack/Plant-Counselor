from __future__ import annotations
from app.ai.skill_base import SkillBase, SkillResult, SkillContext


class SearchConversationSkill(SkillBase):
    name = "search_conversation"
    description = "대화 로그를 검색합니다."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "scope": {"type": "string"},
            "scope_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        def _at(value) -> str:
            if value is None:
                return ""
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        msgs = ctx.conversation_service.search(
            ctx.user_id,
            args["query"],
            args.get("scope") or ctx.scope,
            args.get("scope_id") if args.get("scope") else ctx.scope_id,
            args.get("limit", 10),
        )
        data = [
            {"role": m.role, "text": m.text, "at": _at(getattr(m, "at", ""))} for m in msgs
        ]
        return SkillResult(
            ok=True,
            message=f"{len(data)}개 메시지 찾음",
            data={"messages": data},
        )
