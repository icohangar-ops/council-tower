"""Data Agent tools — query Iceberg, fetch market data, run phases, persist results."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from council.deliberation import run_phase as execute_phase
from council.session import DeliberationSession
from storage import query_deliberations, save_result
from council.deliberation import session_to_result


async def _fetch_market_context_async(topic: str, domain: str) -> str:
    from fetchers import fetch_context_for_topic

    return await fetch_context_for_topic(topic, domain)


def tool_query_deliberations(
    session: DeliberationSession,
    domain: str | None = None,
    topic_contains: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Read prior deliberations from Tower Iceberg (or local fallback)."""
    rows = query_deliberations(domain=domain, topic_contains=topic_contains, limit=limit)
    session.tool_trace.append(
        {
            "tool": "query_deliberations",
            "domain": domain,
            "topic_contains": topic_contains,
            "count": len(rows),
        }
    )
    return {
        "count": len(rows),
        "deliberations": rows,
        "hint": "Use prior confidence scores and summaries to calibrate this run.",
    }


def tool_fetch_market_context(
    session: DeliberationSession,
    sources: str = "auto",
) -> dict[str, Any]:
    """Fetch SEC, commodity, or news context for the session topic."""
    try:
        context = asyncio.run(_fetch_market_context_async(session.topic, session.domain))
    except Exception as exc:
        context = f"Market context fetch failed: {exc}"

    if context and context.strip():
        if session.context:
            session.context = f"{session.context}\n\n{context}"
        else:
            session.context = context

    session.tool_trace.append(
        {
            "tool": "fetch_market_context",
            "sources": sources,
            "context_chars": len(session.context),
        }
    )
    return {
        "sources": sources,
        "context_preview": session.context[:1500],
        "context_chars": len(session.context),
    }


def tool_run_phase(session: DeliberationSession, phase: str) -> dict[str, Any]:
    """Execute one council deliberation phase (ANALYSIS → SUMMARY)."""
    result = execute_phase(session, phase)
    session.tool_trace.append({"tool": "run_phase", "phase": phase.upper(), **result})
    return result


def tool_store_result(session: DeliberationSession) -> dict[str, Any]:
    """Persist the session to Tower Iceberg (or local JSON fallback)."""
    if not session.is_complete():
        remaining = session.phases_remaining()
        return {
            "stored": False,
            "error": f"Deliberation incomplete. Remaining phases: {', '.join(remaining)}",
        }

    deliberation = session_to_result(session)
    storage_info = save_result(deliberation)
    session.stored = True
    session.storage_info = storage_info
    session.deliberation_id = storage_info.get("deliberation_id", "")
    session.tool_trace.append({"tool": "store_result", **storage_info})
    return {"stored": True, **storage_info}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_deliberations",
            "description": (
                "Query prior council deliberations from the Tower Iceberg lakehouse. "
                "Use to find historical decisions, confidence trends, and related topics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Filter by domain: finance, strategy, or general.",
                    },
                    "topic_contains": {
                        "type": "string",
                        "description": "Case-insensitive substring match on deliberation topic.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum rows to return (default 5).",
                        "default": 5,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_market_context",
            "description": (
                "Fetch live market context (SEC filings, commodity prices, news) "
                "for the current deliberation topic and append it to session context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "string",
                        "description": "Source hint: auto, sec, commodity, or news.",
                        "default": "auto",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_phase",
            "description": (
                "Run one council deliberation phase. Valid phases in order: "
                "ANALYSIS, CHALLENGE, VALIDATION, LOCK, SUMMARY. "
                "Each phase invokes the specialist agents for that step."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": ["ANALYSIS", "CHALLENGE", "VALIDATION", "LOCK", "SUMMARY"],
                        "description": "The deliberation phase to execute.",
                    },
                },
                "required": ["phase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_result",
            "description": (
                "Write the completed deliberation to Tower Iceberg tables "
                "(council_deliberations, council_posts). Requires all five phases."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def dispatch_tool(session: DeliberationSession, name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool by name and return JSON-serializable output."""
    if name == "query_deliberations":
        payload = tool_query_deliberations(session, **arguments)
    elif name == "fetch_market_context":
        payload = tool_fetch_market_context(session, **arguments)
    elif name == "run_phase":
        payload = tool_run_phase(session, **arguments)
    elif name == "store_result":
        payload = tool_store_result(session)
    else:
        payload = {"error": f"Unknown tool: {name}"}
    return json.dumps(payload, default=str)
