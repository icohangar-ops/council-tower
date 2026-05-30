"""Council Tower Pipeline — Main orchestration entry point.

This is the script that Tower executes. It:
  1. Reads parameters (topic, domain, context)
  2. Optionally fetches real-world data
  3. Runs the 4-agent council deliberation
  4. Stores results in Tower Iceberg (or local fallback)
  5. Prints a structured summary

Usage with Tower:
    tower run --parameter=topic="Should Apple acquire NVIDIA?"

Usage locally:
    python task.py --topic "Should Apple acquire NVIDIA?" --domain finance
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from council.deliberation import run_deliberation
from council.models import DeliberationResult
from storage import save_result


def get_tower_param(name: str, default: str = "") -> str:
    """Get a parameter from Tower SDK or environment variable.

    Tower injects parameters as environment variables.
    """
    # Tower SDK parameter injection
    try:
        import tower
        val = os.environ.get(f"TOWER__PARAMETER__{name.upper()}", "")
        if val:
            return val
    except ImportError:
        pass

    # Direct environment variable
    return os.environ.get(name.upper(), "") or default


def print_banner():
    """Print the Council pipeline banner."""
    print()
    print(r"  ╔══════════════════════════════════════════════════╗")
    print(r"  ║                                                  ║")
    print(r"  ║   🏛️  COUNCIL — AI Deliberation Pipeline         ║")
    print(r"  ║   Tower Pipeline Engine v1.0                      ║")
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

    # Phase breakdown
    phase_counts = {}
    for post in result.posts:
        phase_counts[post.phase.value] = phase_counts.get(post.phase.value, 0) + 1
    print(f"\n  Phase Breakdown:")
    for phase, count in sorted(phase_counts.items()):
        print(f"    {phase}: {count} posts")

    # Agent confidence summary
    agent_confidences = {}
    for post in result.posts:
        if post.phase.value == "LOCK":
            agent_confidences[post.agent_name] = post.confidence
    if agent_confidences:
        print(f"\n  Final Agent Confidences (LOCK phase):")
        for name, conf in sorted(agent_confidences.items()):
            bar = "█" * int(conf * 20)
            print(f"    {name:20s} {conf:.2f} {bar}")

    # Final summary
    if result.final_summary:
        print(f"\n  {'─' * 56}")
        print(f"  COUNCIL RECOMMENDATION:")
        print(f"  {'─' * 56}")
        # Print first 1000 chars of summary
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
    except Exception as e:
        print(f"[fetch] Data fetch failed: {e}")
        return ""


def main():
    """Main entry point for the Council Tower Pipeline."""
    parser = argparse.ArgumentParser(description="Council AI Deliberation Pipeline")
    parser.add_argument("--topic", type=str, help="Deliberation topic")
    parser.add_argument("--domain", type=str, default="general",
                        help="Domain (finance, strategy, general)")
    parser.add_argument("--context", type=str, default="",
                        help="Additional context for the deliberation")

    args = parser.parse_args()

    # Override with Tower parameters if available
    topic = get_tower_param("topic", args.topic or "")
    domain = get_tower_param("domain", args.domain)
    context = get_tower_param("context", args.context)

    if not topic:
        # Default demo topic
        topic = "Should the Federal Reserve maintain or cut interest rates in Q3 2026?"
        domain = "finance"
        print("[!] No topic provided, using default demo topic.")

    print_banner()

    start_time = time.time()

    # Step 1: Fetch context data
    print("[Step 1/3] Fetching context data...")
    context_data = asyncio.run(fetch_context_async(topic, domain))
    if context_data:
        print(f"  Context fetched ({len(context_data)} chars)")
    else:
        context_data = context
        print("  No external context available, proceeding with topic alone.")

    # Step 2: Run deliberation
    print("\n[Step 2/3] Running council deliberation...")
    result = run_deliberation(
        topic=topic,
        domain=domain,
        context=context_data,
    )

    # Step 3: Store results
    print("\n[Step 3/3] Storing results...")
    storage_info = save_result(result)
    if storage_info.get("mode") == "tower":
        print(f"  Stored in Tower Iceberg: {storage_info.get('deliberation_id', 'N/A')}")
    else:
        print(f"  Stored locally: {storage_info.get('path', 'N/A')}")

    # Print summary
    elapsed = time.time() - start_time
    print_result_summary(result)
    print(f"\n  Total pipeline time: {elapsed:.1f}s")

    # Output JSON for downstream consumers
    output = {
        "deliberation_id": result.created_at.strftime("%Y%m%d%H%M%S"),
        "topic": result.topic,
        "domain": result.domain,
        "status": result.status.value,
        "quality_score": result.quality_score,
        "confidence_score": result.confidence_score,
        "num_posts": len(result.posts),
        "final_summary": result.final_summary,
        "storage": storage_info,
        "pipeline_time_seconds": round(elapsed, 1),
    }

    # Write output JSON
    output_file = os.environ.get("COUNCIL_OUTPUT_FILE", "")
    if output_file:
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Output saved to: {output_file}")

    # Print for Tower logs
    print(f"\n[OUTPUT] {json.dumps(output, indent=2)}")

    return result


if __name__ == "__main__":
    main()
