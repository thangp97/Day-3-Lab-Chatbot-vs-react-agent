"""
VinmecBot Analytics Dashboard
Đọc logs/*.log và hiển thị metrics realtime.

Chạy: streamlit run dashboard.py
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="VinmecBot Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #00836A12, #00A98F08);
    border: 1px solid #00836A25;
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
[data-testid="stMetricLabel"] { font-size: 0.8rem; color: #555; }
.section-header {
    color: #00836A;
    font-size: 1rem;
    font-weight: 600;
    margin: 0.5rem 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Data loading & parsing
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=15)
def load_all_events(log_dir: str = "logs") -> list[dict]:
    """Đọc toàn bộ *.log, parse từng dòng JSON."""
    events: list[dict] = []
    log_path = Path(log_dir)
    if not log_path.exists():
        return events
    for path in sorted(log_path.glob("*.log")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def build_sessions(events: list[dict]) -> list[dict]:
    """Ghép các events thành danh sách sessions hoàn chỉnh."""
    sessions: list[dict] = []
    cur: dict | None = None

    for e in events:
        ev   = e.get("event", "")
        data = e.get("data", {})
        ts   = e.get("timestamp", "")

        if ev == "AGENT_START":
            cur = {
                "start_time":              ts,
                "input":                   data.get("input", ""),
                "model":                   data.get("model", "unknown"),
                "steps":                   [],
                "parse_errors":            0,
                "tool_calls":              [],
                "total_tokens":            0,
                "total_prompt_tokens":     0,
                "total_completion_tokens": 0,
                "estimated_cost_usd":      0.0,
                "total_latency_ms":        0,
                "status":                  "in_progress",
                "answer":                  "",
            }

        elif ev == "AGENT_SESSION_SUMMARY" and cur:
            # Dùng summary đã tính sẵn từ AgentTokenTracker
            cur.update({
                "total_tokens":            data.get("total_tokens",            cur["total_tokens"]),
                "total_prompt_tokens":     data.get("total_prompt_tokens",     0),
                "total_completion_tokens": data.get("total_completion_tokens", 0),
                "estimated_cost_usd":      data.get("estimated_cost_usd",      0.0),
                "total_latency_ms":        data.get("total_latency_ms",        0),
                "model":                   data.get("model",                   cur["model"]),
                "answer":                  data.get("answer_preview",          ""),
                "status":                  data.get("status",                  cur["status"]),
                "steps_used":              data.get("steps_used",              len(cur["steps"])),
            })

        elif ev == "AGENT_STEP" and cur:
            usage      = data.get("usage") or {}
            prompt     = usage.get("prompt_tokens",     0)
            completion = usage.get("completion_tokens", 0)
            total      = usage.get("total_tokens", 0) or (prompt + completion)
            cur["steps"].append({
                "step":              data.get("step"),
                "prompt_tokens":     prompt,
                "completion_tokens": completion,
                "total_tokens":      total,
                "latency_ms":        data.get("latency_ms", 0),
            })
            # Accumulate — may be overwritten later by AGENT_SESSION_SUMMARY
            cur["total_tokens"]            += total
            cur["total_prompt_tokens"]     += prompt
            cur["total_completion_tokens"] += completion
            cur["total_latency_ms"]        += data.get("latency_ms", 0)

        elif ev == "PARSE_ERROR" and cur:
            cur["parse_errors"] += 1

        elif ev == "TOOL_CALL" and cur:
            cur["tool_calls"].append(data.get("tool", "unknown"))

        elif ev == "AGENT_END" and cur:
            cur["status"]    = "completed"
            cur["end_time"]  = ts
            cur["answer"]    = cur.get("answer") or data.get("answer", "")
            cur.setdefault("steps_used", data.get("steps", len(cur["steps"])))
            sessions.append(cur)
            cur = None

        elif ev == "AGENT_TIMEOUT" and cur:
            cur["status"]   = "timeout"
            cur["end_time"] = ts
            cur.setdefault("steps_used", len(cur["steps"]))
            sessions.append(cur)
            cur = None

    if cur:                        # session chưa kết thúc (crash, v.v.)
        cur["status"] = "incomplete"
        cur.setdefault("steps_used", len(cur["steps"]))
        sessions.append(cur)

    return sessions


def build_tool_stats(events: list[dict]) -> dict[str, dict]:
    """Tổng hợp hiệu suất tool từ tất cả TOOL_SESSION_SUMMARY."""
    merged: dict[str, dict] = {}
    for e in events:
        if e.get("event") != "TOOL_SESSION_SUMMARY":
            continue
        for name, stats in e.get("data", {}).get("tools", {}).items():
            if name not in merged:
                merged[name] = {
                    "calls": 0, "hits": 0, "misses": 0,
                    "alias_hits": 0, "lat_total": 0.0, "scores": [],
                }
            m = merged[name]
            calls = stats.get("calls", 0)
            m["calls"]      += calls
            m["hits"]       += stats.get("hit_count",       0)
            m["misses"]     += stats.get("miss_count",       0)
            m["alias_hits"] += stats.get("alias_hit_count",  0)
            m["lat_total"]  += stats.get("latency_avg_ms",   0) * calls
            if stats.get("score_avg") is not None:
                m["scores"].append(stats["score_avg"])

    out: dict[str, dict] = {}
    for name, m in merged.items():
        n = m["calls"] or 1
        out[name] = {
            "calls":          m["calls"],
            "success_rate":   round(m["hits"]       / n * 100, 1),
            "miss_rate":      round(m["misses"]      / n * 100, 1),
            "alias_hit_rate": round(m["alias_hits"]  / n * 100, 1),
            "avg_latency_ms": round(m["lat_total"]   / n, 2),
            "avg_score":      round(sum(m["scores"]) / len(m["scores"]), 2) if m["scores"] else None,
        }
    return out


def count_events_by_type(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        counts[e.get("event", "UNKNOWN")] += 1
    return dict(counts)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏥 VinmecBot")
    st.markdown("**Analytics Dashboard**")
    st.divider()

    log_dir = st.text_input("Thư mục log", value="logs")

    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S')}")
    st.caption("📞 Vinmec: **1800 599 920**")

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

events      = load_all_events(log_dir)
sessions    = build_sessions(events)
tool_stats  = build_tool_stats(events)
event_counts = count_events_by_type(events)

n_sessions   = len(sessions)
n_completed  = sum(1 for s in sessions if s["status"] == "completed")
n_timeout    = sum(1 for s in sessions if s["status"] == "timeout")
total_tokens = sum(s["total_tokens"]       for s in sessions)
total_cost   = sum(s["estimated_cost_usd"] for s in sessions)
success_pct  = n_completed / n_sessions * 100 if n_sessions else 0

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="background:linear-gradient(90deg,#00836A,#00A98F);color:white;
            padding:1.2rem 1.5rem;border-radius:14px;margin-bottom:1rem">
  <h2 style="margin:0">🏥 VinmecBot — Analytics Dashboard</h2>
  <p style="margin:0.3rem 0 0;opacity:0.9;font-size:0.9rem">
    Token usage · Cost · Tool performance · Agent efficiency
  </p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_ov, tab_tok, tab_tool, tab_agent, tab_raw = st.tabs([
    "📊 Overview",
    "🪙 Token & Cost",
    "🔧 Tool Analytics",
    "🤖 Agent Performance",
    "📋 Raw Logs",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

with tab_ov:
    # ── KPI row ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("📨 Sessions",        n_sessions)
    c2.metric("✅ Thành công",       n_completed,
              delta=f"{success_pct:.0f}%" if n_sessions else None)
    c3.metric("⏱️ Timeout",          n_timeout)
    c4.metric("🔤 Tổng tokens",     f"{total_tokens:,}")
    c5.metric("💰 Chi phí ($)",      f"{total_cost:.4f}")
    c6.metric("📋 Log events",       len(events))

    st.divider()

    if sessions:
        st.markdown('<p class="section-header">Sessions gần đây</p>', unsafe_allow_html=True)

        STATUS_ICON = {"completed": "✅", "timeout": "⏱️",
                       "blocked": "🚫", "incomplete": "⚠️", "in_progress": "🔄"}

        rows = []
        for s in reversed(sessions[-30:]):
            inp = s["input"]
            rows.append({
                "Thời gian":     s.get("start_time", "")[:19].replace("T", " "),
                "Input":         (inp[:55] + "…") if len(inp) > 55 else inp,
                "Model":         s["model"],
                "Trạng thái":    STATUS_ICON.get(s["status"], s["status"]),
                "Steps":         s.get("steps_used", len(s["steps"])),
                "Tokens":        s["total_tokens"],
                "Cost ($)":      f"{s['estimated_cost_usd']:.5f}",
                "Parse Errors":  s["parse_errors"],
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    else:
        st.info("Chưa có agent session. Chạy `python main.py` để tạo dữ liệu.")

    # Tool event counts from current log
    if event_counts:
        st.divider()
        st.markdown('<p class="section-header">Phân bố event types trong log</p>',
                    unsafe_allow_html=True)
        st.bar_chart(event_counts)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TOKEN & COST
# ═══════════════════════════════════════════════════════════════════════════════

with tab_tok:
    if not sessions:
        st.info("Chưa có dữ liệu token. Cần chạy agent qua full ReAct loop với LLM thật.")
    else:
        avg_tok  = total_tokens // n_sessions if n_sessions else 0
        avg_cost = total_cost   /  n_sessions if n_sessions else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng tokens",          f"{total_tokens:,}")
        c2.metric("Avg tokens / session", f"{avg_tok:,}")
        c3.metric("Tổng chi phí (USD)",   f"${total_cost:.5f}")
        c4.metric("Avg cost / session",   f"${avg_cost:.5f}")

        st.divider()

        # Per-session breakdown table
        st.markdown('<p class="section-header">Token breakdown theo session</p>',
                    unsafe_allow_html=True)
        tok_rows = []
        for i, s in enumerate(sessions, 1):
            inp = s["input"]
            tok_rows.append({
                "#":                 i,
                "Input":             (inp[:40] + "…") if len(inp) > 40 else inp,
                "Model":             s["model"],
                "Prompt tokens":     s["total_prompt_tokens"],
                "Completion tokens": s["total_completion_tokens"],
                "Total tokens":      s["total_tokens"],
                "Cost (USD)":        f"${s['estimated_cost_usd']:.5f}",
                "Steps":             s.get("steps_used", len(s["steps"])),
                "Latency (ms)":      s["total_latency_ms"],
            })
        st.dataframe(tok_rows, use_container_width=True, hide_index=True)

        st.divider()

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<p class="section-header">Total tokens per session</p>',
                        unsafe_allow_html=True)
            bar_data = {f"S{i+1}": s["total_tokens"] for i, s in enumerate(sessions)}
            st.bar_chart(bar_data, color="#00836A")

        with col_b:
            st.markdown('<p class="section-header">Prompt vs Completion (tổng)</p>',
                        unsafe_allow_html=True)
            t_prompt = sum(s["total_prompt_tokens"]     for s in sessions)
            t_comp   = sum(s["total_completion_tokens"] for s in sessions)
            if t_prompt or t_comp:
                st.bar_chart({"Prompt": t_prompt, "Completion": t_comp}, color="#00A98F")
            else:
                st.info("Cần AGENT_SESSION_SUMMARY để tách prompt/completion tokens.")

    # Pricing reference (always visible)
    st.divider()
    with st.expander("📋 Bảng giá model (tham khảo, USD/1M tokens)"):
        st.table([
            {"Model":              "gemini-1.5-flash",
             "Input ($/1M)":  "$0.075",  "Output ($/1M)": "$0.30"},
            {"Model":              "gemini-1.5-pro",
             "Input ($/1M)":  "$3.50",   "Output ($/1M)": "$10.50"},
            {"Model":              "gemini-2.0-flash",
             "Input ($/1M)":  "$0.10",   "Output ($/1M)": "$0.40"},
            {"Model":              "gpt-4o",
             "Input ($/1M)":  "$2.50",   "Output ($/1M)": "$10.00"},
            {"Model":              "gpt-4o-mini",
             "Input ($/1M)":  "$0.15",   "Output ($/1M)": "$0.60"},
            {"Model":              "Ollama / local",
             "Input ($/1M)":  "FREE",    "Output ($/1M)": "FREE"},
        ])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TOOL ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_tool:
    if not tool_stats:
        st.info("Chưa có TOOL_SESSION_SUMMARY. Chạy tools để tạo dữ liệu.")
    else:
        # Per-tool metric cards
        st.markdown('<p class="section-header">Hiệu suất theo tool</p>',
                    unsafe_allow_html=True)
        TOOL_ICONS = {
            "lookup_surgery_info": "🔍",
            "check_danger_signs":  "🚨",
            "get_checklist":       "📋",
        }
        cols = st.columns(len(tool_stats))
        for col, (name, stats) in zip(cols, tool_stats.items()):
            icon = TOOL_ICONS.get(name, "🔧")
            with col:
                st.markdown(f"**{icon} `{name}`**")
                st.metric("Total calls",    stats["calls"])
                st.metric("Success rate",   f"{stats['success_rate']}%",
                          delta=f"-{stats['miss_rate']}% miss")
                st.metric("Alias hit rate", f"{stats['alias_hit_rate']}%")
                if stats["avg_latency_ms"] is not None:
                    st.metric("Avg latency",    f"{stats['avg_latency_ms']} ms")
                if stats["avg_score"] is not None:
                    st.metric("Avg match score", stats["avg_score"])

        st.divider()

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<p class="section-header">Success rate (%)</p>',
                        unsafe_allow_html=True)
            st.bar_chart(
                {n: s["success_rate"] for n, s in tool_stats.items()},
                color="#00836A",
            )

        with col_b:
            st.markdown('<p class="section-header">Alias hit rate (%)</p>',
                        unsafe_allow_html=True)
            st.bar_chart(
                {n: s["alias_hit_rate"] for n, s in tool_stats.items()},
                color="#00A98F",
            )

    st.divider()

    # TOOL_NO_MATCH viewer
    no_match = [e for e in events if e.get("event") == "TOOL_NO_MATCH"]
    if no_match:
        st.markdown(
            f'<p class="section-header">🔴 TOOL_NO_MATCH — {len(no_match)} lần</p>',
            unsafe_allow_html=True,
        )
        miss_rows = []
        for e in reversed(no_match[-25:]):
            d = e.get("data", {})
            q = d.get("query") or d.get("symptoms") or d.get("stage_input") or "?"
            miss_rows.append({
                "Thời gian": e.get("timestamp", "")[:19].replace("T", " "),
                "Tool":      d.get("tool", "?"),
                "Query":     q[:80],
            })
        st.dataframe(miss_rows, use_container_width=True, hide_index=True)
        st.caption("Các query không match → cân nhắc thêm vào alias dictionary.")
    else:
        st.success("Không có TOOL_NO_MATCH nào trong log hiện tại.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AGENT PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_agent:
    # Error KPIs (always shown, even without sessions)
    parse_err_total = event_counts.get("PARSE_ERROR",    0)
    timeout_total   = event_counts.get("AGENT_TIMEOUT",  0)
    security_total  = event_counts.get("SECURITY_BLOCK", 0)
    no_match_total  = event_counts.get("TOOL_NO_MATCH",  0)

    st.markdown('<p class="section-header">Phân tích lỗi</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟠 PARSE_ERROR",    parse_err_total,
              help="LLM không sinh đúng format Action")
    c2.metric("⛔ AGENT_TIMEOUT",  timeout_total,
              help="Agent vượt max_steps mà chưa ra Final Answer")
    c3.metric("🚫 SECURITY_BLOCK", security_total,
              help="Prompt injection hoặc unsafe medical request")
    c4.metric("🔴 TOOL_NO_MATCH",  no_match_total,
              help="Tool không tìm được kết quả phù hợp")

    if sessions:
        st.divider()

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<p class="section-header">Phân bố số steps / session</p>',
                        unsafe_allow_html=True)
            steps_freq: dict[str, int] = defaultdict(int)
            for s in sessions:
                steps_freq[str(s.get("steps_used", len(s["steps"])))] += 1
            st.bar_chart(dict(sorted(steps_freq.items())), color="#00836A")

        with col_b:
            st.markdown('<p class="section-header">Tool calls phổ biến</p>',
                        unsafe_allow_html=True)
            all_calls = [tc for s in sessions for tc in s["tool_calls"]]
            if all_calls:
                freq: dict[str, int] = defaultdict(int)
                for t in all_calls:
                    freq[t] += 1
                st.bar_chart(dict(freq), color="#00A98F")
            else:
                st.info("Chưa có TOOL_CALL events.")

        st.divider()

        # Detailed session table
        st.markdown('<p class="section-header">Chi tiết từng session</p>',
                    unsafe_allow_html=True)
        STATUS_ICON = {"completed": "✅", "timeout": "⏱️",
                       "blocked": "🚫", "incomplete": "⚠️"}
        detail_rows = []
        for i, s in enumerate(sessions, 1):
            detail_rows.append({
                "#":              i,
                "Status":         STATUS_ICON.get(s["status"], s["status"]),
                "Steps":          s.get("steps_used", len(s["steps"])),
                "Parse Errors":   s["parse_errors"],
                "Tool Calls":     len(s["tool_calls"]),
                "Tokens":         s["total_tokens"],
                "Latency (ms)":   s["total_latency_ms"],
                "Cost ($)":       f"{s['estimated_cost_usd']:.5f}",
                "Model":          s["model"],
            })
        st.dataframe(detail_rows, use_container_width=True, hide_index=True)

    else:
        st.info("Chưa có session data từ agent. Chạy `python main.py` để tạo dữ liệu.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RAW LOGS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_raw:
    if not events:
        st.warning(f"Không tìm thấy file log trong `{log_dir}/`.")
    else:
        all_types = sorted({e.get("event", "UNKNOWN") for e in events})
        col_f, col_s = st.columns([3, 1])

        with col_f:
            selected_types = st.multiselect(
                "Lọc event type",
                options=all_types,
                default=all_types,
            )
        with col_s:
            search = st.text_input("🔍 Tìm kiếm", placeholder="keyword…")

        filtered = [
            e for e in events
            if e.get("event") in selected_types
            and (not search
                 or search.lower() in json.dumps(e, ensure_ascii=False).lower())
        ]

        MAX_DISPLAY = 200
        st.caption(
            f"Hiển thị {min(len(filtered), MAX_DISPLAY):,} / {len(filtered):,} events "
            f"(tổng log: {len(events):,})"
        )

        EVENT_ICONS = {
            "AGENT_START":           "🔵",
            "AGENT_END":             "🟢",
            "AGENT_SESSION_SUMMARY": "💎",
            "AGENT_STEP":            "▶️",
            "AGENT_TIMEOUT":         "⛔",
            "PARSE_ERROR":           "🟠",
            "TOOL_CALL":             "🔧",
            "TOOL_EXECUTED":         "🟡",
            "TOOL_NO_MATCH":         "🔴",
            "TOOL_SESSION_SUMMARY":  "📊",
            "SECURITY_BLOCK":        "🚫",
            "CHAT_API_RESPONSE":     "🌐",
            "CHATBOT_RESPONSE":      "💬",
            "LLM_METRIC":            "📈",
        }

        for e in reversed(filtered[-MAX_DISPLAY:]):
            ev   = e.get("event", "?")
            ts   = e.get("timestamp", "")[:19].replace("T", " ")
            icon = EVENT_ICONS.get(ev, "⚪")
            with st.expander(f"{icon} `{ts}` — **{ev}**", expanded=False):
                st.json(e.get("data", {}))
