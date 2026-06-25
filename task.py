"""Council Tower Pipeline — Main orchestration entry point.

Supports two execution modes (Tower parameter ``mode``):

- ``agent`` (default): Tower Data Agent tool loop — query_deliberations,
  fetch_market_context, run_phase, store_result
- ``pipeline``: Legacy fixed 3-step pipeline (fetch → deliberate → store)

Usage with Tower:
    tower run --parameter=topic="Should Apple acquire NVIDIA?"
    tower run --parameter=mode=agent

Usage locally:
    python task.py --topic "Should Apple acquire NVIDIA?" --domain finance
    python task.py --mode pipeline
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Datadog LLM Observability (no-op unless DD_LLMOBS_ENABLED) ---
from council.observability import init_observability

init_observability("council-tower")

from council.data_agent import run_data_agent
from council.deliberation import run_deliberation
from council.models import DeliberationResult
from storage import save_result


def get_tower_param(name: str, default: str = "") -> str:
    """Get a parameter from Tower SDK or environment variable."""
    val = os.environ.get(f"TOWER__PARAMETER__{name.upper()}", "")
    if val:
        return val
    return os.environ.get(name.upper(), "") or default


def print_banner(mode: str):
    """Print the Council pipeline banner."""
    mode_label = "Data Agent" if mode == "agent" else "Fixed Pipeline"
    print()
    print(r"  ╔══════════════════════════════════════════════════╗")
    print(r"  ║                                                  ║")
    print(r"  ║   🏛️  COUNCIL — AI Deliberation Pipeline         ║")
    print(f"  ║   Tower {mode_label:<31} ║")
    print(r"  ║                                                  ║")
    print(r"  ╚══════════════════════════════════════════════════╝")
    print()


def print_result_summary(result: DeliberationResult):
    """Print a structured summary of the deliberation result."""
    print("\n" + "=" * 60)
    print("  FINAL DELIBERATION SUMMARY")
    print("=" * 60)
    print(f"  Topic:      {result.topic}")
    print(f"  Domain:     {result.domain}")
    print(f"  Status:     {result.status.value}")
    print(f"  Quality:    {result.quality_score}")
    print(f"  Confidence: {result.confidence_score}")
    print(f"  Posts:      {len(result.posts)}")
    print(f"  Time:       {result.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

    phase_counts = {}
    for post in result.posts:
        phase_counts[post.phase.value] = phase_counts.get(post.phase.value, 0) + 1
    print("\n  Phase Breakdown:")
    for phase, count in sorted(phase_counts.items()):
        print(f"    {phase}: {count} posts")

    agent_confidences = {}
    for post in result.posts:
        if post.phase.value == "LOCK":
            agent_confidences[post.agent_name] = post.confidence
    if agent_confidences:
        print("\n  Final Agent Confidences (LOCK phase):")
        for name, conf in sorted(agent_confidences.items()):
            bar = "█" * int(conf * 20)
            print(f"    {name:20s} {conf:.2f} {bar}")

    if result.final_summary:
        print(f"\n  {'─' * 56}")
        print("  COUNCIL RECOMMENDATION:")
        print(f"  {'─' * 56}")
        summary = result.final_summary[:1000]
        for line in summary.split("\n"):
            print(f"  {line}")
        if len(result.final_summary) > 1000:
            print(f"  ... ({len(result.final_summary) - 1000} more characters)")

    print("=" * 60)


async def fetch_context_async(topic: str, domain: str) -> str:
    """Fetch context data for the deliberation topic."""
    try:
        from fetchers import fetch_context_for_topic
        return await fetch_context_for_topic(topic, domain)
    except ImportError:
        print("[fetch] Fetcher module not available, skipping data fetch.")
        return ""
    except Exception as exc:
        print(f"[fetch] Data fetch failed: {exc}")
        return ""


def run_pipeline_mode(topic: str, domain: str, context: str, fetch_data: bool) -> DeliberationResult:
    """Legacy fixed pipeline: fetch → run all phases → store."""
    print("[pipeline] Fetching context data...")
    context_data = context
    if fetch_data:
        fetched = asyncio.run(fetch_context_async(topic, domain))
        if fetched:
            context_data = fetched
            print(f"  Context fetched ({len(context_data)} chars)")

    print("\n[pipeline] Running council deliberation (all phases)...")
    result = run_deliberation(topic=topic, domain=domain, context=context_data)

    print("\n[pipeline] Storing results...")
    storage_info = save_result(result)
    print(f"  Storage: {storage_info}")
    return result


def run_agent_mode(
    topic: str,
    domain: str,
    context: str,
    fetch_data: bool,
    max_steps: int,
) -> tuple[DeliberationResult, dict]:
    """Tower Data Agent mode with tool-calling orchestration."""
    print("[data-agent] Starting tool loop...")
    print("  Tools: query_deliberations, fetch_market_context, run_phase, store_result")
    session, result, agent_summary = run_data_agent(
        topic=topic,
        domain=domain,
        context=context,
        fetch_data=fetch_data,
        max_steps=max_steps,
    )
    meta = {
        "mode": "agent",
        "agent_summary": agent_summary,
        "tool_trace": session.tool_trace,
        "storage": session.storage_info,
        "phases_completed": sorted(session.phases_completed),
    }
    return result, meta


def main():
    """Main entry point for the Council Tower Pipeline."""
    parser = argparse.ArgumentParser(description="Council AI Deliberation Pipeline")
    parser.add_argument("--topic", type=str, help="Deliberation topic")
    parser.add_argument("--domain", type=str, default="general", help="Domain (finance, strategy, general)")
    parser.add_argument("--context", type=str, default="", help="Additional context")
    parser.add_argument("--mode", type=str, default="agent", choices=["agent", "pipeline"])
    parser.add_argument("--max-steps", type=int, default=20, help="Max Data Agent tool loop steps")

    args = parser.parse_args()

    topic = get_tower_param("topic", args.topic or "")
    domain = get_tower_param("domain", args.domain)
    context = get_tower_param("context", args.context)
    mode = get_tower_param("mode", args.mode).lower()
    fetch_data = get_tower_param("fetch_data", "true").lower() in ("1", "true", "yes")
    max_steps = int(get_tower_param("max_agent_steps", str(args.max_steps)))

    if not topic:
        topic = "Should the Federal Reserve maintain or cut interest rates in Q3 2026?"
        domain = "finance"
        print("[!] No topic provided, using default demo topic.")

    print_banner(mode)
    start_time = time.time()

    agent_meta: dict = {}
    if mode == "pipeline":
        result = run_pipeline_mode(topic, domain, context, fetch_data)
        storage_info = {"mode": "pipeline"}
    else:
        result, agent_meta = run_agent_mode(topic, domain, context, fetch_data, max_steps)
        storage_info = agent_meta.get("storage", {})

    elapsed = time.time() - start_time
    print_result_summary(result)
    print(f"\n  Total runtime: {elapsed:.1f}s | Mode: {mode}")

    output = {
        "deliberation_id": agent_meta.get("storage", {}).get("deliberation_id")
        or result.created_at.strftime("%Y%m%d%H%M%S"),
        "topic": result.topic,
        "domain": result.domain,
        "status": result.status.value,
        "quality_score": result.quality_score,
        "confidence_score": result.confidence_score,
        "num_posts": len(result.posts),
        "final_summary": result.final_summary,
        "mode": mode,
        "storage": storage_info,
        "pipeline_time_seconds": round(elapsed, 1),
    }
    if agent_meta:
        output["tool_trace"] = agent_meta.get("tool_trace", [])
        output["agent_summary"] = agent_meta.get("agent_summary", "")

    output_file = get_tower_param("output_file", os.environ.get("COUNCIL_OUTPUT_FILE", ""))
    if output_file:
        with open(output_file, "w") as handle:
            json.dump(output, handle, indent=2)
        print(f"\n  Output saved to: {output_file}")

    print(f"\n[OUTPUT] {json.dumps(output, indent=2)}")
    return result


if __name__ == "__main__":
    main()
