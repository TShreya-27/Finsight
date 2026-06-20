"""Shared helper for building Agno agents consistently."""

from agno.agent import Agent

from app.core.infrastructure import shared_db, shared_memory
from app.core.settings import settings
from app.guardrails.custom import OutputSanityGuardrail

MODEL = settings.AGNO_MODEL


def build_agent(*, name: str, instructions: str, response_model=None, tools=None, pre_hooks=None, post_hooks=None, tool_hooks=None, model: str | None = None):
    """Create a configured Agno Agent with shared DB and shared memory."""
    effective_pre_hooks = [*(pre_hooks or [OutputSanityGuardrail()])]
    return Agent(
        name=name,
        model=model or MODEL,
        instructions=instructions,
        output_schema=response_model,
        tools=tools or [],
        pre_hooks=effective_pre_hooks,
        post_hooks=[*(post_hooks or [])],
        tool_hooks=tool_hooks or [],
        db=shared_db,
        memory_manager=shared_memory,
        enable_agentic_memory=True,
        update_memory_on_run=True,
        markdown=False,
    )
