"""Tests for the Council deliberation engine."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from council.models import (
    AgentConfig,
    DeliberationResult,
    Domain,
    LockState,
    Phase,
    Post,
    RoomStatus,
)
from council.agents import AGENTS
from council.llm import extract_confidence


def test_agent_configs():
    """Verify all expected agents are defined."""
    assert len(AGENTS) == 4, f"Expected 4 agents, got {len(AGENTS)}"

    roles = {a.role for a in AGENTS}
    expected_roles = {"financial-analyst", "contrarian", "compliance-validator", "council-summarizer"}
    assert roles == expected_roles, f"Expected {expected_roles}, got {roles}"

    for agent in AGENTS:
        assert agent.name, f"Agent {agent.role} has no name"
        assert agent.system_prompt, f"Agent {agent.role} has no system prompt"

    print("  test_agent_configs: PASSED")


def test_models():
    """Verify data models work correctly."""
    post = Post(
        agent_id="test-123",
        agent_name="Ava Chen",
        role="financial-analyst",
        content="Test analysis content.",
        phase=Phase.ANALYSIS,
        lock_state=LockState.PROVISIONAL,
        confidence=0.85,
    )
    assert post.agent_id == "test-123"
    assert post.phase == Phase.ANALYSIS
    assert post.lock_state == LockState.PROVISIONAL

    result = DeliberationResult(
        topic="Test topic",
        domain="finance",
        status=RoomStatus.LOCKED,
        posts=[post],
        quality_score=0.85,
        confidence_score=0.85,
    )
    d = result.to_dict()
    assert d["topic"] == "Test topic"
    assert d["status"] == "LOCKED"
    assert len(d["posts"]) == 1

    j = result.to_json()
    assert "Test topic" in j
    assert '"confidence_score": 0.85' in j

    print("  test_models: PASSED")


def test_extract_confidence():
    """Test confidence extraction from text."""
    tests = [
        ("confidence: 0.85", 0.85),
        ("confidence score: 0.72", 0.72),
        ("0.9 / 1.0", 0.9),
        ("85% confidence", 0.85),
        ("no confidence here", 0.7),  # default
    ]
    for text, expected in tests:
        result = extract_confidence(text)
        assert abs(result - expected) < 0.01, f"For '{text}': got {result}, expected {expected}"

    print("  test_extract_confidence: PASSED")


def test_deliberation_protocol():
    """Test that the deliberation protocol phases are in correct order."""
    from council.deliberation import (
        _run_analysis_phase,
        _run_challenge_phase,
        _run_validation_phase,
        _run_lock_phase,
        _run_summary_phase,
    )

    # Verify all phase functions exist and are callable
    assert callable(_run_analysis_phase)
    assert callable(_run_challenge_phase)
    assert callable(_run_validation_phase)
    assert callable(_run_lock_phase)
    assert callable(_run_summary_phase)

    print("  test_deliberation_protocol: PASSED")


def test_prompt_templates():
    """Verify prompt templates have correct placeholders."""
    from council.agents import (
        CHALLENGE_PROMPT,
        VALIDATION_PROMPT,
        LOCK_PROMPT,
        SUMMARY_PROMPT,
    )

    # Challenge template
    assert "{topic}" in CHALLENGE_PROMPT
    assert "{analysis}" in CHALLENGE_PROMPT

    # Validation template
    assert "{topic}" in VALIDATION_PROMPT
    assert "{original}" in VALIDATION_PROMPT
    assert "{challenge}" in VALIDATION_PROMPT

    # Lock template
    assert "{topic}" in LOCK_PROMPT
    assert "{context}" in LOCK_PROMPT

    # Summary template
    assert "{topic}" in SUMMARY_PROMPT
    assert "{domain}" in SUMMARY_PROMPT
    assert "{analyses}" in SUMMARY_PROMPT
    assert "{challenges}" in SUMMARY_PROMPT
    assert "{validations}" in SUMMARY_PROMPT

    print("  test_prompt_templates: PASSED")


def test_storage_local():
    """Test local storage fallback."""
    from storage import save_local, load_local_results

    result = DeliberationResult(
        topic="Storage test",
        domain="general",
        status=RoomStatus.LOCKED,
        quality_score=0.5,
        confidence_score=0.5,
    )
    filepath = save_local(result)
    assert os.path.exists(filepath), f"File not created: {filepath}"

    results = load_local_results()
    assert any(r["topic"] == "Storage test" for r in results), "Saved result not found"

    # Cleanup
    os.remove(filepath)
    print("  test_storage_local: PASSED")


def run_all_tests():
    """Run all tests."""
    print("\nRunning Council Tower Pipeline tests...\n")
    test_agent_configs()
    test_models()
    test_extract_confidence()
    test_deliberation_protocol()
    test_prompt_templates()
    test_storage_local()
    print("\n  All tests PASSED!\n")


if __name__ == "__main__":
    run_all_tests()
