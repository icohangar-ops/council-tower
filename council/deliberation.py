"""Council deliberation engine — the core multi-agent reasoning pipeline.

This module implements the structured deliberation protocol used by Council:
  Phase 1: ANALYSIS   — Each specialist agent analyzes the topic independently
  Phase 2: CHALLENGE  — The contrarian challenges other agents' analyses
  Phase 3: VALIDATION — Challenged agents respond and defend their positions
  Phase 4: LOCK       — All agents commit to their final positions
  Phase 5: SUMMARY    — The summarizer synthesizes all contributions

The protocol ensures adversarial rigor: no analysis goes unchallenged, and
every agent must either defend or revise their position before locking.
"""

import time
import uuid
from datetime import datetime

from council.agents import (
    AGENTS,
    CHALLENGE_PROMPT,
    LOCK_PROMPT,
    SUMMARY_PROMPT,
    VALIDATION_PROMPT,
)
from council.llm import call_llm, extract_confidence
from council.models import (
    AgentConfig,
    DeliberationResult,
    Domain,
    LockState,
    Phase,
    Post,
    RoomStatus,
)


def _generate_agent_id() -> str:
    return str(uuid.uuid4())[:8]


def _make_analysis_prompt(agent: AgentConfig, topic: str, domain: str, context: str = "") -> str:
    """Build the user prompt for Phase 1 analysis."""
    parts = [
        f"Analyze the following decision:\n\n",
        f"**Topic:** {topic}\n",
        f"**Domain:** {domain}\n",
    ]
    if context:
        parts.append(f"**Context:** {context}\n")
    parts.append(f"\nProvide your {agent.role} analysis.")
    return "".join(parts)


def _run_analysis_phase(
    agents: list[AgentConfig],
    topic: str,
    domain: str,
    context: str,
) -> tuple[list[Post], list[tuple[str, str, str]]]:
    """Phase 1: Each non-summarizer agent produces an independent analysis.

    Returns:
        (posts, analysis_records) where each record is (agent_id, name, role, content)
    """
    analyst_agents = [a for a in agents if a.role != "council-summarizer"]
    posts: list[Post] = []
    records: list[tuple[str, str, str]] = []  # (agent_id, name, content)

    for agent in analyst_agents:
        agent_id = _generate_agent_id()
        user_prompt = _make_analysis_prompt(agent, topic, domain, context)
        content = call_llm(agent.system_prompt, user_prompt)
        confidence = extract_confidence(content)

        post = Post(
            agent_id=agent_id,
            agent_name=agent.name,
            role=agent.role,
            content=content,
            phase=Phase.ANALYSIS,
            lock_state=LockState.PROVISIONAL,
            confidence=confidence,
        )
        posts.append(post)
        records.append((agent_id, agent.name, content))

        print(f"  [ANALYSIS] {agent.name} ({agent.role}) — confidence {confidence:.2f}")

    return posts, records


def _run_challenge_phase(
    agents: list[AgentConfig],
    topic: str,
    analysis_records: list[tuple[str, str, str]],
) -> tuple[list[Post], str]:
    """Phase 2: The contrarian challenges other analyses.

    Returns:
        (challenge_posts, challenge_content)
    """
    contrarian = next((a for a in agents if a.role == "contrarian"), None)
    if not contrarian:
        return [], ""

    other_analyses = "\n\n---\n\n".join(
        f"**{name} ({role}):**\n{content}"
        for agent_id, name, content in analysis_records
        if any(a.role == role for a in agents if a.name == name)
        for role in [next((a.role for a in agents if a.name == name), "")]
    )

    # Re-filter to exclude contrarian's own analysis
    contrarian_name = contrarian.name
    filtered = [
        f"**{name} ({next((a.role for a in agents if a.name == name), '')}):**\n{content}"
        for agent_id, name, content in analysis_records
        if name != contrarian_name
    ]
    analyses_text = "\n\n---\n\n".join(filtered)

    challenge_content = call_llm(
        contrarian.system_prompt,
        CHALLENGE_PROMPT.format(topic=topic, analysis=analyses_text),
    )
    confidence = extract_confidence(challenge_content)

    challenge_post = Post(
        agent_id=_generate_agent_id(),
        agent_name=contrarian.name,
        role="contrarian",
        content=challenge_content,
        phase=Phase.CHALLENGE,
        lock_state=LockState.PROVISIONAL,
        confidence=confidence,
    )

    print(f"  [CHALLENGE] {contrarian.name} — confidence {confidence:.2f}")

    return [challenge_post], challenge_content


def _run_validation_phase(
    agents: list[AgentConfig],
    topic: str,
    analysis_records: list[tuple[str, str, str]],
    challenge_content: str,
) -> list[Post]:
    """Phase 3: Non-contrarian agents respond to the challenge."""
    posts: list[Post] = []
    contrarian_name = next((a.name for a in agents if a.role == "contrarian"), "")

    for agent_id, name, content in analysis_records:
        if name == contrarian_name:
            continue

        agent = next((a for a in agents if a.name == name), None)
        if not agent:
            continue

        validation_content = call_llm(
            agent.system_prompt,
            VALIDATION_PROMPT.format(
                topic=topic,
                original=content,
                challenge=challenge_content,
            ),
        )
        confidence = extract_confidence(validation_content)

        post = Post(
            agent_id=agent_id,
            agent_name=agent.name,
            role=agent.role,
            content=validation_content,
            phase=Phase.VALIDATION,
            lock_state=LockState.PROVISIONAL,
            confidence=confidence,
        )
        posts.append(post)

        print(f"  [VALIDATION] {agent.name} — confidence {confidence:.2f}")

    return posts


def _run_lock_phase(
    agents: list[AgentConfig],
    topic: str,
    all_posts: list[Post],
) -> list[Post]:
    """Phase 4: All agents lock their final positions after reviewing all phases."""
    posts: list[Post] = []

    for agent in agents:
        agent_posts = [p for p in all_posts if p.agent_name == agent.name]
        if not agent_posts:
            continue

        posts_summary = "\n\n---\n\n".join(
            f"**[{p.phase.value}]** {p.content}" for p in agent_posts
        )

        lock_content = call_llm(
            agent.system_prompt,
            LOCK_PROMPT.format(topic=topic, context=posts_summary),
        )
        confidence = extract_confidence(lock_content)

        post = Post(
            agent_id=_generate_agent_id(),
            agent_name=agent.name,
            role=agent.role,
            content=lock_content,
            phase=Phase.LOCK,
            lock_state=LockState.LOCKED,
            confidence=confidence,
        )
        posts.append(post)

        print(f"  [LOCK] {agent.name} — confidence {confidence:.2f}")

    return posts


def _run_summary_phase(
    agents: list[AgentConfig],
    topic: str,
    domain: str,
    all_posts: list[Post],
) -> tuple[str, float]:
    """Phase 5: The summarizer produces a final synthesis."""
    summarizer = next((a for a in agents if a.role == "council-summarizer"), None)
    if not summarizer:
        return "", 0.0

    analyses = "\n\n".join(
        f"**{p.agent_name} ({p.role}):** {p.content}"
        for p in all_posts
        if p.phase == Phase.ANALYSIS
    )
    challenges = "\n\n".join(
        f"**{p.agent_name} ({p.role}):** {p.content}"
        for p in all_posts
        if p.phase == Phase.CHALLENGE
    )
    validations = "\n\n".join(
        f"**{p.agent_name} ({p.role}):** {p.content}"
        for p in all_posts
        if p.phase == Phase.VALIDATION
    )

    summary_content = call_llm(
        summarizer.system_prompt,
        SUMMARY_PROMPT.format(
            topic=topic,
            domain=domain,
            analyses=analyses or "No analyses produced.",
            challenges=challenges or "No challenges produced.",
            validations=validations or "No validations produced.",
        ),
    )
    confidence = extract_confidence(summary_content)

    print(f"  [SUMMARY] {summarizer.name} — confidence {confidence:.2f}")

    return summary_content, confidence


def run_deliberation(
    topic: str,
    domain: str = "general",
    context: str = "",
    agents: list[AgentConfig] | None = None,
) -> DeliberationResult:
    """Execute a full council deliberation cycle.

    This is the main entry point for the deliberation engine. It runs all five
    phases sequentially: ANALYSIS → CHALLENGE → VALIDATION → LOCK → SUMMARY.

    Args:
        topic: The decision topic or question to deliberate on.
        domain: The domain (finance, strategy, general) for context.
        context: Additional context or data to inform the deliberation.
        agents: Optional custom agent list. Defaults to the standard 4-agent council.

    Returns:
        A DeliberationResult containing all posts, the final summary, and scores.
    """
    agents = agents or AGENTS
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"Council Deliberation — {domain.upper()}")
    print(f"Topic: {topic}")
    print(f"Agents: {', '.join(a.name for a in agents)}")
    print(f"{'='*60}\n")

    all_posts: list[Post] = []

    # Phase 1: ANALYSIS
    print("[Phase 1] ANALYSIS")
    analysis_posts, analysis_records = _run_analysis_phase(agents, topic, domain, context)
    all_posts.extend(analysis_posts)

    # Phase 2: CHALLENGE
    print("\n[Phase 2] CHALLENGE")
    challenge_posts, challenge_content = _run_challenge_phase(agents, topic, analysis_records)
    all_posts.extend(challenge_posts)

    # Phase 3: VALIDATION
    print("\n[Phase 3] VALIDATION")
    validation_posts = _run_validation_phase(agents, topic, analysis_records, challenge_content)
    all_posts.extend(validation_posts)

    # Phase 4: LOCK
    print("\n[Phase 4] LOCK")
    lock_posts = _run_lock_phase(agents, topic, all_posts)
    all_posts.extend(lock_posts)

    # Phase 5: SUMMARY
    print("\n[Phase 5] SUMMARY")
    final_summary, summary_confidence = _run_summary_phase(agents, topic, domain, all_posts)

    # Calculate scores
    lock_confidences = [p.confidence for p in lock_posts if p.confidence > 0]
    avg_confidence = (
        sum(lock_confidences) / len(lock_confidences)
        if lock_confidences
        else summary_confidence
    )

    elapsed = time.time() - start_time

    result = DeliberationResult(
        topic=topic,
        domain=domain,
        status=RoomStatus.LOCKED,
        posts=all_posts,
        final_summary=final_summary,
        quality_score=round(avg_confidence, 2),
        confidence_score=round(avg_confidence, 2),
        created_at=datetime.utcnow(),
    )

    print(f"\n{'='*60}")
    print(f"Deliberation complete in {elapsed:.1f}s")
    print(f"Posts: {len(all_posts)}")
    print(f"Quality: {result.quality_score}")
    print(f"Confidence: {result.confidence_score}")
    print(f"{'='*60}\n")

    return result
