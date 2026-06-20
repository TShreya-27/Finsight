"""Hooks for session-start and tool execution logging."""

from __future__ import annotations

import json
import time
from datetime import datetime

from app.core.infrastructure import redis_client


def push_activity(agent_name: str, session_id: str, tool: str, input_preview: str, output_preview: str, duration_ms: int) -> None:
    """Append a tool activity event to Redis."""
    event = {
        "agent": agent_name,
        "session_id": session_id,
        "tool": tool,
        "input_preview": input_preview,
        "output_preview": output_preview,
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    redis_client.rpush(f"agent_activity:{agent_name}:{session_id}", json.dumps(event))


def session_start_hook(*args, **kwargs):
    """Session-start hook used by agents and workflows."""
    agent_name = kwargs.get("agent_name", "unknown")
    session_id = kwargs.get("session_id", "unknown")
    push_activity(agent_name, session_id, "session_start", str(kwargs.get("input", ""))[:200], "", 0)


def tool_logger(agent_name: str, session_id: str):
    """Bind a specific agent/session to a generic tool hook."""
    def hook(function_name, function_call, arguments):
        start = time.perf_counter()
        result = function_call(**arguments)
        duration_ms = int((time.perf_counter() - start) * 1000)
        push_activity(agent_name, session_id, function_name, str(arguments)[:200], str(result)[:200], duration_ms)
        return result
    return hook
