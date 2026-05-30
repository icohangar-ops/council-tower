"""Agent definitions and system prompts for the Council deliberation engine.

Each agent has a distinct role and personality. The council uses a structured
deliberation protocol: ANALYSIS → CHALLENGE → VALIDATION → LOCK → SUMMARY.

Agents:
  - financial-analyst (Ava Chen): Rigorous financial analysis
  - contrarian (Marcus Webb): Adversarial challenge of dominant views
  - compliance-validator (Priya Sharma): Regulatory and compliance assessment
  - council-summarizer (David Kim): Synthesis and final recommendation
"""

from council.agents import AGENTS

__all__ = ["AGENTS"]

# Re-export for convenience
