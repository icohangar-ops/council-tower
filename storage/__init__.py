"""Tower Iceberg lakehouse storage for deliberation results.

Provides functions to:
  - Create Iceberg tables for council data
  - Write deliberation results to tables
  - Read historical deliberations for analytics
"""

from __future__ import annotations

import json
import pyarrow as pa

# Try importing tower SDK (available when running in Tower)
try:
    import tower
    HAS_TOWER = True
except ImportError:
    HAS_TOWER = False
    print("[storage] Tower SDK not available — running in local mode.")

# ── Schema Definitions ────────────────────────────────────────────────────

DELIBERATIONS_SCHEMA = pa.schema([
    ("deliberation_id", pa.string()),
    ("topic", pa.string()),
    ("domain", pa.string()),
    ("status", pa.string()),
    ("final_summary", pa.string()),
    ("quality_score", pa.float64()),
    ("confidence_score", pa.float64()),
    ("num_posts", pa.int64()),
    ("created_at", pa.string()),
])

POSTS_SCHEMA = pa.schema([
    ("post_id", pa.string()),
    ("deliberation_id", pa.string()),
    ("agent_name", pa.string()),
    ("role", pa.string()),
    ("content", pa.string()),
    ("phase", pa.string()),
    ("lock_state", pa.string()),
    ("confidence", pa.float64()),
    ("created_at", pa.string()),
])

# ── Local Fallback (CSV/JSON files) ──────────────────────────────────────

import os
from datetime import datetime

LOCAL_DATA_DIR = os.environ.get("COUNCIL_DATA_DIR", "./data")


def _ensure_local_dir():
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)


def save_local(result) -> str:
    """Save deliberation result to local JSON file (fallback mode)."""
    _ensure_local_dir()
    filepath = os.path.join(
        LOCAL_DATA_DIR,
        f"deliberation_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(filepath, "w") as f:
        f.write(result.to_json())
    print(f"[storage] Saved to {filepath}")
    return filepath


def load_local_results(limit: int = 50) -> list[dict]:
    """Load recent local deliberation results."""
    _ensure_local_dir()
    results = []
    for filename in sorted(os.listdir(LOCAL_DATA_DIR))[-limit:]:
        if filename.endswith(".json"):
            filepath = os.path.join(LOCAL_DATA_DIR, filename)
            with open(filepath) as f:
                results.append(json.load(f))
    return results


# ── Tower Iceberg Storage ────────────────────────────────────────────────

def save_to_tower(result) -> dict:
    """Save deliberation results to Tower Iceberg tables.

    Creates two tables:
      - council_deliberations: One row per deliberation (summary level)
      - council_posts: One row per agent post (detail level)

    Args:
        result: A DeliberationResult instance.

    Returns:
        Dict with table names and rows affected.
    """
    if not HAS_TOWER:
        print("[storage] Tower SDK not available, saving locally instead.")
        filepath = save_local(result)
        return {"mode": "local", "path": filepath}

    deliberation_id = f"del-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Write deliberations table
    try:
        del_table = (
            tower.tables("council_deliberations")
            .create_if_not_exists(DELIBERATIONS_SCHEMA)
        )
        del_table = del_table.upsert(
            pa.table({
                "deliberation_id": [deliberation_id],
                "topic": [result.topic],
                "domain": [result.domain],
                "status": [result.status.value],
                "final_summary": [result.final_summary],
                "quality_score": [result.quality_score],
                "confidence_score": [result.confidence_score],
                "num_posts": [len(result.posts)],
                "created_at": [result.created_at.isoformat()],
            }),
            join_cols=["deliberation_id"],
        )
        del_rows = del_table.rows_affected()
    except Exception as e:
        print(f"[storage] Error writing deliberations table: {e}")
        del_rows = {"inserted": 0, "updated": 0}

    # Write posts table
    post_rows = {"inserted": 0, "updated": 0}
    if result.posts:
        try:
            post_table = (
                tower.tables("council_posts")
                .create_if_not_exists(POSTS_SCHEMA)
            )
            post_table = post_table.upsert(
                pa.table({
                    "post_id": [f"post-{i}" for i in range(len(result.posts))],
                    "deliberation_id": [deliberation_id] * len(result.posts),
                    "agent_name": [p.agent_name for p in result.posts],
                    "role": [p.role for p in result.posts],
                    "content": [p.content for p in result.posts],
                    "phase": [p.phase.value for p in result.posts],
                    "lock_state": [p.lock_state.value for p in result.posts],
                    "confidence": [p.confidence for p in result.posts],
                    "created_at": [p.created_at.isoformat() for p in result.posts],
                }),
                join_cols=["post_id"],
            )
            post_rows = post_table.rows_affected()
        except Exception as e:
            print(f"[storage] Error writing posts table: {e}")

    print(
        f"[storage] Saved to Tower Iceberg: "
        f"{del_rows} deliberations, {post_rows} posts"
    )

    return {
        "mode": "tower",
        "deliberation_id": deliberation_id,
        "deliberations_rows": del_rows,
        "posts_rows": post_rows,
    }


def read_tower_deliberations() -> list[dict]:
    """Read all deliberation results from Tower Iceberg."""
    if not HAS_TOWER:
        print("[storage] Tower SDK not available, loading local results.")
        return load_local_results()

    try:
        table = tower.tables("council_deliberations").load()
        df = table.to_polars().collect()
        return df.to_dicts()
    except Exception as e:
        print(f"[storage] Error reading deliberations: {e}")
        return load_local_results()


def read_tower_posts() -> list[dict]:
    """Read all agent posts from Tower Iceberg."""
    if not HAS_TOWER:
        print("[storage] Tower SDK not available — no posts to read.")
        return []

    try:
        table = tower.tables("council_posts").load()
        df = table.to_polars().collect()
        return df.to_dicts()
    except Exception as e:
        print(f"[storage] Error reading posts: {e}")
        return []


def save_result(result) -> dict:
    """Save a deliberation result (auto-detects Tower vs local mode).

    This is the main entry point for storage operations.
    """
    if HAS_TOWER:
        return save_to_tower(result)
    return {"mode": "local", "path": save_local(result)}
