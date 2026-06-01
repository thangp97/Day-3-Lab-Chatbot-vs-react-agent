# Individual Report — Lab 3: Chatbot vs ReAct Agent

- **Student Name**: BaoVu2k4
- **Role**: TV1 — Tools Engineer
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

### Modules Implemented

| File | Dòng | Mô tả |
|:-----|:-----|:------|
| `src/tools/medical_tools.py` | ~520 | Knowledge Base, Alias Dict, Danger Signs, Checklist, 3 tool functions, TOOLS registry |
| `src/telemetry/tool_metrics.py` | ~120 | Session-level metrics tracker cho tool calls |

---

### 1.1 `src/tools/medical_tools.py`

#### Knowledge Base (`_KB`)
25 entries bao phủ toàn bộ câu hỏi thường gặp về phẫu thuật cắt ruột thừa:
nhịn ăn, xét nghiệm, thuốc dừng, ăn uống sau mổ, vết mổ, tái khám, gây mê, chi phí, thể thao, đi làm, sẹo, biến chứng, viêm ruột thừa, nội soi so mổ mở, trẻ em, mang thai, v.v.

#### Alias Dictionary (`_ALIASES`)
50 cụm từ mapping → canonical KB key. Ví dụ:
```python
"khi nào tắm"  → "tắm"
"ăn gì sau"    → "ăn uống sau mổ"
"cắt chỉ"      → "tái khám"
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
#   "total_tool_calls": 13,
#   "overall_success_rate": 0.769,
#   "tools": {
#     "lookup_surgery_info": {
#       "calls": 7, "success_rate": 0.857,
#       "score_avg": 2.6, "score_max": 5.375,
#       "alias_hit_count": 1, "alias_hit_rate": 0.143
#     },
#     "check_danger_signs": { "calls": 3, "success_rate": 0.667 },
#     "get_checklist":       { "calls": 3, "success_rate": 0.667 }
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

## II. Debugging Case Study (10 Points)

### Case 1 — Bug phát hiện: Compound keyword không match trong `check_danger_signs`

**Input của người dùng**: `"Vết mổ bị đỏ và sưng, tôi có cần đến viện không?"`

**Log quan sát được** (trước khi fix):
```json
{
  "timestamp": "2026-06-01T07:02:11.445Z",
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "check_danger_signs",
    "symptoms": "Vết mổ bị đỏ và sưng, tôi có cần đến viện không?",
    "matched": [],
    "highest_severity": null,
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

**Log sau khi fix**:
```json
{
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "check_danger_signs",
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

**Log quan sát được** (trước khi fix):
```json
{
  "event": "TOOL_EXECUTED",
  "data": {
    "tool": "lookup_surgery_info",
    "matched_keys": ["ăn uống sau mổ", "tắm"],
    "top_score": 1,
    "elapsed_ms": 0
  }
}
```

**Output sai**: Trả về thông tin chế độ ăn (entry `"ăn uống sau mổ"`) thay vì thông tin tắm rửa.

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

**Log sau khi fix**:
```json
{
  "event": "TOOL_EXECUTED",
  "data": {
    "matched_keys": ["tắm"],
    "top_score": 1.5,
    "elapsed_ms": 0
  }
}
```
**Output đúng**: `"Được tắm nhẹ sau 48 giờ hậu phẫu..."`

---

### Tổng kết debugging

| Bug | Symptom | Root Cause | Fix |
|:----|:--------|:-----------|:----|
| Compound keyword | `matched: []` khi query có liên từ | Exact substring match | All-words matching |
| Score tie-break | Wrong KB entry returned | `int` score, stable sort favors earlier entry | `float` + specificity |

**Bài học**: Thiết kế tool cho LLM Agent cần test với **natural language variation** — người dùng không dùng keyword chính xác. Silent failure (trả về sai thay vì báo lỗi) nguy hiểm hơn explicit error vì agent không nhận ra cần retry.

---

## III. Personal Insights: Chatbot vs ReAct Agent (10 Points)

### 1. Reasoning: Thought block giúp ích gì?

Chatbot trả lời trực tiếp từ LLM memory — không có bước "kiểm tra lại". Khi tôi test:
- Chatbot với query `"nhịn ăn bao lâu"` → đôi khi trả lời `"4 tiếng"` (hallucination — số thực là 6 tiếng).
- Agent với cùng query → `Thought: cần tra cứu KB` → `Action: lookup_surgery_info("nhịn ăn")` → `Observation: "6 tiếng..."` → `Final Answer` dựa trên fact thật.

`Thought` block bắt buộc LLM **khai báo kế hoạch** trước khi hành động — giúp debug dễ hơn và giảm hallucination vì LLM phải dùng tool thay vì tự bịa.

### 2. Reliability: Khi nào Agent tệ hơn Chatbot?

| Tình huống | Chatbot | Agent |
|:-----------|:--------|:------|
| Câu hỏi đơn giản (1 fact) | Nhanh, đủ | Chậm hơn (1–2 tool calls) |
| Tool TOOL_NO_MATCH | — | Trả về fallback, không escalate |
| PARSE_ERROR (LLM sai format) | Không áp dụng | Loop thêm step, tốn token |
| Câu hỏi ngoài domain (tim, thận...) | Hallucinate nhưng tự tin | Trả về "chưa có thông tin" |

**Agent tệ hơn khi**: câu hỏi rất ngắn/đơn giản — latency cao hơn không đáng. Và khi LLM không tuân thủ format Action → PARSE_ERROR → lặp loop không hiệu quả (v1 issue, giải quyết bởi TV2 trong v2 với few-shot).

### 3. Observation: Feedback loop ảnh hưởng thế nào?

Observation thực sự thay đổi hành vi của agent trong cùng một conversation. Ví dụ:

```
User: Vết mổ bị đỏ, tôi có bị sốt 39 độ nữa
Thought: Có hai triệu chứng, cần kiểm tra nguy hiểm.
Action: check_danger_signs("vết mổ đỏ và sốt cao 39 độ")
Observation: [NGUY HIỂM] Vết mổ đỏ... [NGUY HIỂM] Sốt trên 38.5°C... ⚠️ 1800 599 920
Thought: Đây là tình trạng nguy hiểm, cần hướng dẫn đến viện ngay.
Final Answer: ...
```

Nếu Observation trả về `CHÚ Ý` thôi, Final Answer sẽ khác hẳn so với `NGUY HIỂM`. Chatbot không có cơ chế này — chỉ trả lời dựa trên training data.

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
> **2 bugs đã phát hiện và fix** trong quá trình tự test: compound keyword matching và score tiebreaker.
>
> **Tests**: Toàn bộ logic tools pass **25/25** assertions trước khi submit.
