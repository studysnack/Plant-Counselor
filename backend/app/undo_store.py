"""Small in-process undo stack for recent destructive user actions.

This is intentionally short-lived. It gives users an immediate "oops" recovery
for deletes/status changes without introducing a new migration yet.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass
class UndoAction:
    id: str
    kind: str
    label: str
    payload: dict[str, Any]


_STACKS: defaultdict[str, deque[UndoAction]] = defaultdict(lambda: deque(maxlen=20))


def push(user_id: str, kind: str, label: str, payload: dict[str, Any]) -> UndoAction:
    action = UndoAction(id=str(uuid4()), kind=kind, label=label, payload=payload)
    _STACKS[user_id].append(action)
    return action


def pop(user_id: str, action_id: str | None = None) -> UndoAction | None:
    stack = _STACKS[user_id]
    if not stack:
        return None
    if action_id is None:
        return stack.pop()
    for index in range(len(stack) - 1, -1, -1):
        action = stack[index]
        if action.id == action_id:
            del stack[index]
            return action
    return None
