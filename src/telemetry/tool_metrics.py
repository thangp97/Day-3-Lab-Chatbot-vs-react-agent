# -*- coding: utf-8 -*-
"""
Tool-level metrics tracker — industry-grade monitoring for ReAct tool calls.

Tracks per-tool and session-level statistics:
  - Call volume & success/failure rates
  - Latency distribution (avg, min, max)
  - Match score quality (for lookup tools)
  - Alias system utilisation rate
  - Session cost estimate (time-weighted)

Usage:
    from src.telemetry.tool_metrics import tool_tracker

    # Record inside each tool function:
    tool_tracker.record(tool_name, matched=True, elapsed_ms=2, score=4, alias_used=True)

    # Get aggregate report at end of session:
    tool_tracker.log_summary()
"""

import time
from typing import Optional
from src.telemetry.logger import logger


class ToolMetricsTracker:
    """Session-level performance tracker for tool calls."""

    def __init__(self) -> None:
        self._session_start: float = time.time()
        # Per-tool raw data
        self._stats: dict[str, dict] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    def record(
        self,
        tool_name: str,
        *,
        matched: bool,
        elapsed_ms: int,
        score: int = 0,
        alias_used: bool = False,
    ) -> None:
        """
        Record one tool invocation.

        Args:
            tool_name:   Name of the tool called.
            matched:     True if the tool found a result, False if it returned a fallback.
            elapsed_ms:  Execution time in milliseconds.
            score:       Relevance score (only meaningful for lookup_surgery_info).
            alias_used:  True if the alias dictionary helped resolve the query.
        """
        if tool_name not in self._stats:
            self._stats[tool_name] = {
                "calls":       0,
                "hits":        0,   # matched == True
                "misses":      0,   # matched == False
                "alias_hits":  0,
                "total_ms":    0,
                "min_ms":      float("inf"),
                "max_ms":      0,
                "scores":      [],  # relevance scores for lookup tool
            }
        s = self._stats[tool_name]
        s["calls"]      += 1
        s["total_ms"]   += elapsed_ms
        s["min_ms"]      = min(s["min_ms"], elapsed_ms)
        s["max_ms"]      = max(s["max_ms"], elapsed_ms)

        if matched:
            s["hits"] += 1
            if score > 0:
                s["scores"].append(score)
        else:
            s["misses"] += 1

        if alias_used:
            s["alias_hits"] += 1

    def summary(self) -> dict:
        """
        Compute aggregate statistics for all tools in this session.
        Returns a structured dict suitable for JSON serialisation.
        """
        session_s = round(time.time() - self._session_start, 3)
        per_tool: dict[str, dict] = {}

        total_calls = total_hits = 0

        for name, s in self._stats.items():
            calls = s["calls"]
            hits  = s["hits"]
            total_calls += calls
            total_hits  += hits

            scores = s["scores"]
            per_tool[name] = {
                "calls":           calls,
                "hit_count":       hits,
                "miss_count":      s["misses"],
                "success_rate":    _pct(hits, calls),
                "miss_rate":       _pct(s["misses"], calls),
                "alias_hit_count": s["alias_hits"],
                "alias_hit_rate":  _pct(s["alias_hits"], calls),
                "latency_avg_ms":  _avg(s["total_ms"], calls),
                "latency_min_ms":  s["min_ms"] if calls else 0,
                "latency_max_ms":  s["max_ms"],
                "score_avg":       _avg(sum(scores), len(scores)) if scores else None,
                "score_max":       max(scores) if scores else None,
            }

        return {
            "session_duration_s":    session_s,
            "total_tool_calls":      total_calls,
            "overall_success_rate":  _pct(total_hits, total_calls),
            "overall_miss_rate":     _pct(total_calls - total_hits, total_calls),
            "tools":                 per_tool,
        }

    def log_summary(self) -> dict:
        """Compute summary, emit a TOOL_SESSION_SUMMARY log event, and return the dict."""
        data = self.summary()
        logger.log_event("TOOL_SESSION_SUMMARY", data)
        return data

    def reset(self) -> None:
        """Clear all accumulated stats and restart session timer."""
        self.__init__()

    # ── Convenience ────────────────────────────────────────────────────────

    def get_tool_stats(self, tool_name: str) -> Optional[dict]:
        """Return raw stats for a single tool, or None if not yet called."""
        return self._stats.get(tool_name)


# ── Helpers ────────────────────────────────────────────────────────────────

def _pct(numerator: int | float, denominator: int | float) -> float:
    """Return numerator/denominator rounded to 3 decimal places, or 0.0 if denom is 0."""
    return round(numerator / denominator, 3) if denominator else 0.0


def _avg(total: int | float, count: int) -> float:
    """Return total/count rounded to 2 decimal places, or 0.0 if count is 0."""
    return round(total / count, 2) if count else 0.0


# ── Global instance ────────────────────────────────────────────────────────
tool_tracker = ToolMetricsTracker()
