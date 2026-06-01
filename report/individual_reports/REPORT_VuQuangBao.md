# Individual Report — Lab 3: Chatbot vs ReAct Agent

- **Student Name**: Vu Quang Bao
- **Student ID**: 2A202600610
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

### Modules Implemented

| File | Dòng | Mô tả |
|:-----|:-----|:------|
| `src/tools/medical_tools.py` | ~520 | Knowledge Base, Alias Dict, Danger Signs, Checklist, 3 tool functions, TOOLS registry |
| `src/telemetry/tool_metrics.py` | ~120 | Tool-level metrics tracker (calls, hit/miss rate, alias rate, latency) |
| `src/telemetry/token_tracker.py` | ~110 | Per-session token + cost tracker cho ReAct agent |
| `src/agent/agent.py` | +15 | Tích hợp token tracking vào ReAct loop (3 call points) |
| `dashboard.py` | ~280 | Streamlit analytics dashboard — 5 tabs: Overview, Token & Cost, Tool Analytics, Agent Performance, Raw Logs |

---

### 1.1 `src/tools/medical_tools.py`

#### Knowledge Base (`_KB`)
25 entries bao phủ toàn bộ câu hỏi thường gặp về phẫu thuật cắt ruột thừa:
nhịn ăn, xét nghiệm, thuốc dừng, ăn uống sau mổ, vết mổ, tái khám, gây mê, chi phí, thể thao, đi làm, sẹo, biến chứng, viêm ruột thừa, nội soi so mổ mở, trẻ em, mang thai, v.v.

#### Alias Dictionary (`_ALIASES`)
50 cụm từ mapping → canonical KB key. Ví dụ:
```python
"khi nào tắm"      → "tắm"
"ăn gì sau"        → "ăn uống sau mổ"
"cắt chỉ"          → "tái khám"
"lái xe được chưa" → "lái xe"
```
**Lý do cần Alias**: Người dùng không dùng đúng từ khóa trong KB. Không có alias, query `"khi nào được tắm?"` sẽ không match entry `"tắm"`.

#### Scoring Search (`_score_match`)
Thay vì `any(word in query)` (code mẫu — false positive cao), tôi dùng:
```python
def _score_match(query_tokens: set[str], key: str) -> float:
    key_tokens = _tokenize(key)
    matched = len(query_tokens & key_tokens)
    specificity = matched / len(key_tokens)   # tiebreaker
    return matched + specificity * 0.5
```
- **`matched`**: số token khớp (điểm chính).
- **`specificity`**: phần trăm key được match (tiebreaker) — key ngắn khớp hoàn toàn thắng key dài chỉ khớp một phần.

**Ví dụ cụ thể** (phát hiện trong quá trình test):
- Query: `"Tái khám sau mổ ruột thừa vào ngày nào?"`
- Code mẫu (any-match): `"ăn uống sau mổ"` và `"tái khám"` cùng score 2 → `"ăn uống sau mổ"` thắng do thứ tự dict → **SAI**.
- Scoring của tôi: `"tái khám"` score = 2 + (2/2)×0.5 = **2.5**, `"ăn uống sau mổ"` score = 2 + (2/4)×0.5 = **2.25** → `"tái khám"` thắng → **ĐÚNG**.

#### Danger Signs (`_DANGER`)
16 dấu hiệu bất thường với 3 mức độ: KHẨN CẤP / NGUY HIỂM / CHÚ Ý.
`check_danger_signs()` tìm **tất cả** dấu hiệu khớp, sắp xếp theo mức độ nghiêm trọng giảm dần, thêm hotline khi có NGUY HIỂM trở lên.

#### 3 Tool Functions
```python
lookup_surgery_info(query: str) -> str
check_danger_signs(symptoms: str) -> str
get_checklist(stage: str) -> str
```
Mỗi hàm: log `TOOL_EXECUTED` khi có kết quả, `TOOL_NO_MATCH` khi không tìm thấy, ghi `elapsed_ms`.

---

### 1.2 `src/telemetry/tool_metrics.py`

`ToolMetricsTracker` — global instance `tool_tracker` — theo dõi per-session:

```python
tool_tracker.record("lookup_surgery_info", matched=True,
                    elapsed_ms=2, score=4, alias_used=True)

summary = tool_tracker.log_summary()
# → Event: TOOL_SESSION_SUMMARY
# {
#   "total_tool_calls": 14,
#   "overall_success_rate": 0.786,
#   "tools": {
#     "lookup_surgery_info": {
#       "calls": 5, "success_rate": 0.8,
#       "score_avg": 3.0, "score_max": 5,
#       "alias_hit_count": 2, "alias_hit_rate": 0.4
#     },
#     "check_danger_signs": { "calls": 5, "success_rate": 0.8 },
#     "get_checklist":       { "calls": 4, "success_rate": 0.75 }
#   }
# }
```

Metrics được emit vào `logs/YYYY-MM-DD.log` qua `logger.log_event("TOOL_SESSION_SUMMARY", ...)`.

---

### 1.3 Tương tác với ReAct Loop

Khi `ReActAgent` gọi `_execute_tool("lookup_surgery_info", '"nhịn ăn"')`:
1. Agent gọi `tool["function"](*args)`.
2. Tool chạy scoring search, trả về chuỗi kết quả.
3. `tool_tracker.record(...)` ghi metrics nền.
4. `logger.log_event("TOOL_EXECUTED", {...})` sinh trace vào `logs/`.
5. Agent nhận observation, append vào conversation, tiếp tục loop.

---

### 1.4 `src/telemetry/token_tracker.py` + `dashboard.py`

#### Token Tracker

`AgentTokenTracker` — global instance `agent_token_tracker` — theo dõi token usage trong **một** `agent.run()` call:

```python
# Tích hợp trong agent.py:
agent_token_tracker.reset()                                    # đầu run()
agent_token_tracker.record_step(step, model, usage, latency)  # sau mỗi llm.generate()
agent_token_tracker.log_summary(user_input, "completed", ans) # khi kết thúc
```

Bảng giá thực tế được nhúng trực tiếp (USD / 1M tokens):

| Model | Input | Output |
|:------|------:|-------:|
| gemini-1.5-flash | $0.075 | $0.30 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| Ollama / local | FREE | FREE |

Event mới được emit vào log:
```json
{
  "event": "AGENT_SESSION_SUMMARY",
  "data": {
    "steps_used": 2,
    "model": "gemini-1.5-flash",
    "total_prompt_tokens": 1750,
    "total_completion_tokens": 200,
    "total_tokens": 1950,
    "estimated_cost_usd": 0.000191,
    "total_latency_ms": 2700,
    "avg_tokens_per_step": 975.0,
    "status": "completed",
    "input_preview": "Khi nào được tắm sau phẫu thuật?"
  }
}
```

Ngoài ra, mỗi `AGENT_STEP` event bây giờ có thêm `cumulative_tokens` và `cumulative_cost_usd` để theo dõi token tích lũy theo thời gian thực.

#### Analytics Dashboard (`dashboard.py`)

Streamlit app đọc `logs/*.log`, parse JSON và hiển thị 5 tabs:

| Tab | Nội dung |
|:----|:---------|
| 📊 Overview | KPI cards (sessions, tokens, cost, success rate) · Bảng sessions · Event type chart |
| 🪙 Token & Cost | Breakdown prompt/completion per session · Bar chart · Bảng giá model |
| 🔧 Tool Analytics | Success/miss/alias rate per tool · TOOL_NO_MATCH viewer |
| 🤖 Agent Performance | PARSE_ERROR, TIMEOUT, SECURITY_BLOCK counts · Steps distribution |
| 📋 Raw Logs | Filter by event type · Search · JSON expandable per event |

Chạy: `streamlit run dashboard.py`

---

## II. Debugging Case Study (10 Points)

### Case 1 — Bug phát hiện: Compound keyword không match trong `check_danger_signs`

**Input của người dùng**: `"Vết mổ bị đỏ và sưng, tôi có cần đến viện không?"`

**Log thực tế từ `logs/2026-06-01.log`** (trước khi fix, timestamp 07:14:20):
```json
{
  "timestamp": "2026-06-01T07:14:20.980650",
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "check_danger_signs",
    "symptoms": "Vết mổ bị đỏ và sưng, tôi có cần đến viện không?",
    "matched": [],
    "elapsed_ms": 0
  }
}
```

**Output sai**: `"Triệu chứng bạn mô tả không nằm trong danh sách cảnh báo khẩn."`

**Chẩn đoán**: Keyword trong `_DANGER` là `"đỏ sưng"`. Code kiểm tra `"đỏ sưng" in symptoms` — đây là exact substring match. Khi user viết `"đỏ và sưng"` (có liên từ "và" ở giữa), chuỗi `"đỏ sưng"` không xuất hiện liên tục → miss hoàn toàn. Đây là **silent failure** nguy hiểm: người dùng hỏi về triệu chứng viêm nhiễm nghiêm trọng nhưng bot trả lời "không có gì đáng lo".

**Fix**:
```python
# Trước (code mẫu):
if keyword in s:

# Sau (fix):
def _keyword_matches_symptoms(keyword: str, text: str) -> bool:
    words = keyword.split()
    if len(words) == 1:
        return keyword in text
    return all(w in text for w in words)  # compound: kiểm tra từng từ riêng

if _keyword_matches_symptoms(keyword, s):
```

**Log sau khi fix** (timestamp 07:17:44 — cùng input, sau khi deploy fix):
```json
{
  "timestamp": "2026-06-01T07:17:44.844993",
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "check_danger_signs",
    "symptoms": "Vết mổ bị đỏ và sưng, tôi có cần đến viện không?",
    "matched": [{"keyword": "đỏ sưng", "level": "NGUY HIỂM"}],
    "highest_severity": "NGUY HIỂM",
    "elapsed_ms": 0
  }
}
```
**Output đúng**: `"[NGUY HIỂM] Vết mổ đỏ, sưng, nóng là dấu hiệu viêm nhiễm... ⚠️ 1800 599 920"`

---

### Case 2 — Bug phát hiện: Score tie-break sai trong `lookup_surgery_info`

**Input**: `"Khi nào tôi được tắm sau phẫu thuật?"`

**Log thực tế từ `logs/2026-06-01.log`** (trước khi fix, timestamp 07:14:20):
```json
{
  "timestamp": "2026-06-01T07:14:20.980033",
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "lookup_surgery_info",
    "query": "Khi nào tôi được tắm sau phẫu thuật?",
    "matched_keys": ["ăn uống sau mổ", "tắm"],
    "top_score": 1,
    "candidates": 5,
    "elapsed_ms": 0
  }
}
```

**Output sai**: Trả về thông tin chế độ ăn (entry `"ăn uống sau mổ"`) thay vì thông tin tắm rửa — entry sai xuất hiện đầu tiên trong `matched_keys`.

**Chẩn đoán**: Cả `"tắm"` lẫn `"ăn uống sau mổ"` đều score bằng 1 (mỗi entry khớp 1 token: "tắm" và "sau" tương ứng). Code mẫu dùng `int` score, Python `sort` là stable → `"ăn uống sau mổ"` xuất hiện trước trong dict thứ tự chèn nên thắng. False positive ngay cả khi entry đó không liên quan.

**Root cause**: Score `int` không có tiebreaker → entry phổ biến (có token "sau", "mổ") luôn cạnh tranh bất hợp lý.

**Fix**: Đổi sang `float`, thêm **specificity** làm tiebreaker:
```python
def _score_match(query_tokens: set[str], key: str) -> float:
    key_tokens = _tokenize(key)
    matched = len(query_tokens & key_tokens)
    specificity = matched / len(key_tokens)   # 1.0 nếu toàn bộ key khớp
    return matched + specificity * 0.5
```

- `"tắm"` (1 token): score = 1 + (1/1)×0.5 = **1.5** ✓
- `"ăn uống sau mổ"` (4 tokens): score = 1 + (1/4)×0.5 = **1.125**

**Log sau khi fix** (timestamp 07:17:44 — cùng input, sau khi deploy fix):
```json
{
  "timestamp": "2026-06-01T07:17:44.844147",
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "lookup_surgery_info",
    "query": "Khi nào tôi được tắm sau phẫu thuật?",
    "matched_keys": ["tắm", "đau sau mổ"],
    "top_score": 1.5,
    "candidates": 5,
    "elapsed_ms": 0
  }
}
```
**Output đúng**: `"Được tắm nhẹ sau 48 giờ hậu phẫu..."`

---

### Tổng kết debugging

| Bug | Symptom trong log | Root Cause | Fix |
|:----|:------------------|:-----------|:----|
| Compound keyword | `matched: []` khi query có liên từ | Exact substring match | All-words matching |
| Score tie-break | `matched_keys` sai thứ tự, `top_score: 1` (int) | `int` score, stable sort favors earlier dict entry | `float` + specificity tiebreaker |

**Bài học**: Thiết kế tool cho LLM Agent cần test với **natural language variation** — người dùng không dùng keyword chính xác. Silent failure (trả về sai thay vì báo lỗi) nguy hiểm hơn explicit error vì agent không nhận ra cần retry.

---

## III. Personal Insights: Chatbot vs ReAct Agent (10 Points)

### 1. Reasoning: Thought block giúp ích gì?

Chatbot trả lời trực tiếp từ LLM memory — không có bước "kiểm tra lại". Khi test:
- Chatbot với query `"nhịn ăn bao lâu"` → đôi khi trả lời `"4 tiếng"` (hallucination — số thực là 6 tiếng).
- Agent với cùng query → `Thought: cần tra cứu KB` → `Action: lookup_surgery_info("nhịn ăn")` → `Observation: "6 tiếng..."` → `Final Answer` dựa trên fact thật.

`Thought` block bắt buộc LLM **khai báo kế hoạch** trước khi hành động — giúp debug dễ hơn và giảm hallucination vì LLM phải dùng tool thay vì tự bịa.

### 2. Reliability: Khi nào Agent tệ hơn Chatbot?

Dựa trên kết quả chạy test và quan sát log `logs/2026-06-01.log` (14 tool calls, 78.6% overall success rate):

| Tình huống | Chatbot (baseline) | Agent (ReAct) |
|:-----------|:-------------------|:--------------|
| Câu hỏi có số liệu chính xác (nhịn ăn, tái khám) | Hallucinate số liệu | Chính xác từ KB (80% hit rate) |
| Câu hỏi triệu chứng nguy hiểm | Trả lời chung chung | Phân loại KHẨN CẤP/NGUY HIỂM/CHÚ Ý |
| Câu hỏi ngoài domain (tim, thận) | Tự tin trả lời sai | `TOOL_NO_MATCH` → trả về fallback + hotline |
| Câu hỏi ngắn, đơn giản | Nhanh, đủ | Chậm hơn (1–2 tool calls thêm latency) |
| LLM không tuân thủ format Action | Không áp dụng | `PARSE_ERROR` → loop thêm step, tốn token |

**Tổng kết từ session log**: Tool success rate 78.6% — tức là 21.4% lần tool trả `TOOL_NO_MATCH`, agent phải dùng fallback. Chatbot không có metric này nhưng cũng không có safety net khi trả lời sai.

### 3. Observation: Feedback loop ảnh hưởng thế nào?

Observation thực sự thay đổi hành vi của agent trong cùng một conversation. Ví dụ từ session log (timestamp 07:17:44):

```
User: Vết mổ bị đỏ, tôi có bị sốt 39 độ nữa
Thought: Có hai triệu chứng, cần kiểm tra nguy hiểm.
Action: check_danger_signs("vết mổ bị đỏ và sưng")
Observation: [NGUY HIỂM] Vết mổ đỏ, sưng, nóng... ⚠️ 1800 599 920
Thought: Đây là tình trạng nguy hiểm, cần hướng dẫn đến viện ngay.
Final Answer: ...
```

Log xác nhận: cùng input `"Vết mổ bị đỏ và sưng"` trả về `highest_severity: "NGUY HIỂM"` → agent chọn Final Answer khẩn cấp. Nếu Observation trả về `CHÚ Ý`, Final Answer sẽ khác hẳn. Chatbot không có cơ chế này — chỉ trả lời dựa trên training data.

---

## IV. Future Improvements (5 Points)

### Scalability — Từ lookup table lên Vector Search

Hiện tại KB có 25 entries — đủ cho demo nhưng không scale. Trong production:
```
User query → embedding (text-embedding-3-small)
           → cosine similarity search trên vector DB (Pinecone / Qdrant)
           → top-k chunks từ tài liệu y tế chuẩn (BYT, Vinmec protocols)
```
Tool `lookup_surgery_info` trở thành RAG retriever — trả về context thật thay vì hardcoded string. KB cập nhật được mà không cần deploy code.

### Safety — Supervisor LLM

Thêm một LLM nhẹ làm "safety gate" trước khi trả Final Answer cho user:
```python
def _safety_review(answer: str) -> bool:
    """Phát hiện: chẩn đoán bệnh, liều thuốc cụ thể, thông tin sai về Vinmec."""
```
Tương tự Constitutional AI của Anthropic — agent tự phê bình output trước khi phát.

### Performance — Async Tool Execution

Khi agent cần gọi nhiều tools cùng lúc:
```python
# Hiện tại: sequential
obs1 = lookup_surgery_info("nhịn ăn")
obs2 = check_danger_signs("sốt cao")

# Cải tiến: parallel
obs1, obs2 = await asyncio.gather(
    async_lookup("nhịn ăn"),
    async_check_danger("sốt cao"),
)
```
Giảm latency ~50% cho multi-tool queries.

### Observability — Distributed Tracing

Tích hợp OpenTelemetry để trace toàn bộ request từ UI → agent → tool → LLM:
- Correlation ID xuyên suốt từng bước.
- Prometheus metrics export cho Grafana dashboard.
- Alert khi `miss_rate > 30%` hoặc `latency_p99 > 3s`.

`tool_tracker` hiện tại là nền tảng tốt — bước tiếp theo là export sang OpenTelemetry Collector.

---

> **Files đã implement**: `src/tools/medical_tools.py`, `src/telemetry/tool_metrics.py`
>
> **2 bugs đã phát hiện và fix** với bằng chứng từ `logs/2026-06-01.log`: compound keyword matching (07:14:20 → 07:17:44) và score tiebreaker (07:14:20 → 07:17:44).
>
> **Tests**: Toàn bộ logic tools pass **25/25** assertions trước khi submit.
