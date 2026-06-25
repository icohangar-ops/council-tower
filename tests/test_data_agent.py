"""Tests for the Tower Data Agent tool layer."""

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from council.session import DeliberationSession
from council.tools import dispatch_tool, TOOL_DEFINITIONS
from council.deliberation import run_phase, session_to_result
from council.models import RoomStatus
from storage import query_deliberations, save_local


def test_tool_definitions():
    names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
    assert names == {
        "query_deliberations",
        "fetch_market_context",
        "run_phase",
        "store_result",
    }
    print("  test_tool_definitions: PASSED")


def test_query_deliberations_local():
    result = save_local(
        session_to_result(
            DeliberationSession(topic="Rate cut deliberation", domain="finance")
        )
    )
    assert os.path.exists(result)
    rows = query_deliberations(domain="finance", topic_contains="rate", limit=5)
    assert any("Rate cut" in row.get("topic", "") for row in rows)
    os.remove(result)
    print("  test_query_deliberations_local: PASSED")


def test_run_phase_requires_order():
    session = DeliberationSession(topic="Test order", domain="general")
    challenge = run_phase(session, "CHALLENGE")
    assert challenge["status"] == "error"
    print("  test_run_phase_requires_order: PASSED")


@patch("council.deliberation.call_llm", return_value="Analysis with confidence: 0.8")
def test_run_phase_analysis(mock_llm):
    session = DeliberationSession(topic="Test analysis", domain="finance", context="ctx")
    outcome = run_phase(session, "ANALYSIS")
    assert outcome["status"] == "completed"
    assert "ANALYSIS" in session.phases_completed
    assert len(session.posts) >= 1
    mock_llm.assert_called()
    print("  test_run_phase_analysis: PASSED")


def test_dispatch_tool_query():
    session = DeliberationSession(topic="Hello world", domain="general")
    payload = json.loads(dispatch_tool(session, "query_deliberations", {"limit": 1}))
    assert "count" in payload
    print("  test_dispatch_tool_query: PASSED")


@patch("council.deliberation.call_llm", return_value="Mock content confidence: 0.75")
def test_deterministic_data_agent(mock_llm, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)

    from council.data_agent import run_data_agent

    session, result, summary = run_data_agent(
        topic="Deterministic agent test",
        domain="general",
        fetch_data=False,
        max_steps=5,
    )
    assert session.is_complete()
    assert result.status == RoomStatus.LOCKED
    assert any(entry["tool"] == "run_phase" for entry in session.tool_trace)
    assert summary
    print("  test_deterministic_data_agent: PASSED")


def run_all_tests():
    print("\nRunning Council Data Agent tests...\n")
    test_tool_definitions()
    test_query_deliberations_local()
    test_run_phase_requires_order()
    test_run_phase_analysis()
    test_dispatch_tool_query()
    test_deterministic_data_agent()
    print("\n  All Data Agent tests PASSED!\n")


if __name__ == "__main__":
    run_all_tests()
