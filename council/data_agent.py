"""Tower Data Agent — LLM tool-calling loop over council deliberation tools."""

from __future__ import annotations

import json
import os
from typing import Any

from council.llm import call_llm_with_tools
from council.session import DeliberationSession
from council.tools import TOOL_DEFINITIONS, dispatch_tool
from council.deliberation import session_to_result
from council.models import DeliberationResult

ORCHESTRATOR_SYSTEM_PROMPT = """\
You are the Council Data Agent — an orchestrator for a multi-agent financial \
deliberation pipeline on the Tower platform.

Your job is to answer the user's decision question by calling tools in a \
reasoning loop. Ground every decision in real data from the lakehouse and \
live market fetchers when available.

Available tools:
- query_deliberations: Read prior council results from Tower Iceberg
- fetch_market_context: Pull SEC filings, commodity prices, or news for the topic
- run_phase: Execute one council phase (ANALYSIS, CHALLENGE, VALIDATION, LOCK, SUMMARY)
- store_result: Persist completed deliberations to Iceberg

Recommended strategy:
1. query_deliberations for similar past topics (optional but valuable)
2. fetch_market_context when domain is finance or the topic mentions tickers/commodities
3. run_phase for each phase in order: ANALYSIS → CHALLENGE → VALIDATION → LOCK → SUMMARY
4. store_result after all five phases succeed
5. Respond with the final council recommendation and key metrics

Do not skip phases. Do not call store_result until SUMMARY is complete.
When done, provide a concise executive summary for the user.
"""


def _default_tool_plan(session: DeliberationSession, fetch_data: bool) -> list[dict[str, Any]]:
    """Deterministic fallback when the orchestrator LLM has no API key."""
    steps: list[dict[str, Any]] = [{"tool": "query_deliberations", "args": {"domain": session.domain, "limit": 3}}]
    if fetch_data:
        steps.append({"tool": "fetch_market_context", "args": {"sources": "auto"}})
    for phase in ["ANALYSIS", "CHALLENGE", "VALIDATION", "LOCK", "SUMMARY"]:
        steps.append({"tool": "run_phase", "args": {"phase": phase}})
    steps.append({"tool": "store_result", "args": {}})
    return steps


def run_data_agent(
    topic: str,
    domain: str = "finance",
    context: str = "",
    fetch_data: bool = True,
    max_steps: int = 20,
) -> tuple[DeliberationSession, DeliberationResult, str]:
    """Run the Tower Data Agent reasoning loop.

    Uses OpenAI-compatible tool calling when an API key is configured; otherwise
    executes a deterministic tool plan (same tools, no LLM orchestration).
    """
    session = DeliberationSession(topic=topic, domain=domain, context=context)
    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ZHIPU_API_KEY"))

    user_prompt = (
        f"Deliberate on this decision.\n\n"
        f"Topic: {topic}\n"
        f"Domain: {domain}\n"
    )
    if context:
        user_prompt += f"Additional context from parameters:\n{context}\n"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    final_text = ""

    if not has_key:
        print("[data-agent] No LLM API key — running deterministic tool plan.")
        for step in _default_tool_plan(session, fetch_data=fetch_data):
            output = dispatch_tool(session, step["tool"], step["args"])
            print(f"  [tool] {step['tool']} → {output[:200]}")
        final_text = session.final_summary or "Deliberation completed (deterministic plan)."
    else:
        for step_idx in range(max_steps):
            response = call_llm_with_tools(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"  [data-agent step {step_idx + 1}] {name}({args})")
                    output = dispatch_tool(session, name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": output,
                        }
                    )
                continue

            final_text = message.content or ""
            if session.is_complete() and session.stored:
                break
            if final_text and session.is_complete():
                if not session.stored:
                    dispatch_tool(session, "store_result", {})
                break

        if session.is_complete() and not session.stored:
            dispatch_tool(session, "store_result", {})

        if not final_text:
            final_text = session.final_summary or "Council deliberation finished."

    result = session_to_result(session)
    return session, result, final_text
