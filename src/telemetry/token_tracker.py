"""
Per-session token tracker for the ReAct agent.

Accumulates token usage across every LLM step in one agent.run() call,
estimates USD cost using current model pricing, and emits
AGENT_SESSION_SUMMARY to the structured log at end of session.

Usage (called automatically by ReActAgent):
    agent_token_tracker.reset()
    agent_token_tracker.record_step(step, model_name, usage_dict, latency_ms)
    agent_token_tracker.log_summary(user_input, "completed", answer)
"""

import time
from src.telemetry.logger import logger

# ── Pricing table (USD per 1 million tokens) ─────────────────────────────────
# Source: official pricing pages, approximate as of 2026.
# Local/unknown models are treated as free.

_PRICING: dict[str, dict[str, float]] = {
    # Gemini
    "gemini-1.5-flash":      {"input": 0.075,  "output": 0.300},
    "gemini-1.5-flash-8b":   {"input": 0.0375, "output": 0.150},
    "gemini-1.5-pro":        {"input": 3.500,  "output": 10.50},
    "gemini-2.0-flash":      {"input": 0.100,  "output": 0.400},
    "gemini-2.0-flash-lite": {"input": 0.075,  "output": 0.300},
    # OpenAI
    "gpt-4o":                {"input": 2.500,  "output": 10.00},
    "gpt-4o-mini":           {"input": 0.150,  "output": 0.600},
    "gpt-3.5-turbo":         {"input": 0.500,  "output": 1.500},
    # Claude
    "claude-3-5-sonnet":     {"input": 3.000,  "output": 15.00},
    "claude-3-haiku":        {"input": 0.250,  "output": 1.250},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for one LLM call. Returns 0.0 for local/unknown models."""
    pricing = _PRICING.get(model.lower())
    if not pricing:
        return 0.0
    return round(
        (prompt_tokens    / 1_000_000) * pricing["input"]
        + (completion_tokens / 1_000_000) * pricing["output"],
        8,
    )


# ── Tracker class ─────────────────────────────────────────────────────────────

class AgentTokenTracker:
    """
    Accumulates token usage across all LLM steps in a single agent.run() call.
    Thread-safe for single-threaded agent use (one call at a time).
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Call at the start of every agent.run() to clear previous session data."""
        self._steps: list[dict] = []
        self._session_start: float = time.time()

    def record_step(
        self,
        step: int,
        model: str,
        usage: dict | None,
        latency_ms: int,
    ) -> None:
        """Record token usage for one LLM call (one ReAct step)."""
        usage = usage or {}
        prompt     = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total      = usage.get("total_tokens", 0) or (prompt + completion)
        cost       = _estimate_cost(model, prompt, completion)

        self._steps.append({
            "step":              step,
            "model":             model,
            "prompt_tokens":     prompt,
            "completion_tokens": completion,
            "total_tokens":      total,
            "latency_ms":        latency_ms,
            "cost_usd":          cost,
        })

    def get_summary(self) -> dict:
        """Aggregate per-step data into session totals. Returns {} if no steps recorded."""
        if not self._steps:
            return {}

        n           = len(self._steps)
        t_prompt    = sum(s["prompt_tokens"]     for s in self._steps)
        t_comp      = sum(s["completion_tokens"]  for s in self._steps)
        t_tokens    = sum(s["total_tokens"]       for s in self._steps)
        t_cost      = sum(s["cost_usd"]           for s in self._steps)
        t_latency   = sum(s["latency_ms"]         for s in self._steps)

        return {
            "steps_used":               n,
            "model":                    self._steps[0]["model"],
            "total_prompt_tokens":      t_prompt,
            "total_completion_tokens":  t_comp,
            "total_tokens":             t_tokens,
            "estimated_cost_usd":       round(t_cost, 6),
            "total_latency_ms":         t_latency,
            "avg_tokens_per_step":      round(t_tokens  / n, 1),
            "avg_latency_per_step_ms":  round(t_latency / n, 1),
            "steps":                    self._steps,
        }

    def log_summary(
        self,
        user_input: str,
        status: str,
        answer: str = "",
    ) -> dict:
        """
        Compute summary, emit AGENT_SESSION_SUMMARY to the log, and return the dict.

        Args:
            user_input: original user query (stored as 120-char preview).
            status:     "completed" | "timeout" | "blocked".
            answer:     final answer text (stored as 120-char preview).
        """
        summary = self.get_summary()
        if not summary:
            return {}

        summary["input_preview"]  = user_input[:120]
        summary["status"]         = status
        summary["answer_preview"] = answer[:120]

        logger.log_event("AGENT_SESSION_SUMMARY", summary)
        return summary

    # ── Convenience ──────────────────────────────────────────────────────────

    @property
    def total_tokens(self) -> int:
        return sum(s["total_tokens"] for s in self._steps)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(s["cost_usd"] for s in self._steps), 6)

    @property
    def steps_recorded(self) -> int:
        return len(self._steps)


# ── Global instance ───────────────────────────────────────────────────────────
# Reset by ReActAgent.run() at the start of each call.
agent_token_tracker = AgentTokenTracker()
