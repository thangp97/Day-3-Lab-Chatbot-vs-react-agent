# VinmecBot — Luồng hoạt động của cả 3 thành viên

> Dự án: Day-3-Lab-Chatbot-vs-react-agent  
> Phân tích dựa trên code thực tế sau khi pull ngày 2026-06-01

---

## Kiến trúc tổng thể

```
                       REACT UI / CLI
                            │
              ┌─────────────┴─────────────┐
              │                           │
     CHATBOT BASELINE             REACT AGENT LOOP
       chatbot.py                  src/agent/agent.py
     (Ollama, no tools)           (TV2 — Thought→Action→Obs)
              │                           │
              │                 ┌─────────┼─────────┐
              │                 ▼         ▼         ▼
              │          lookup_info  check_danger  get_checklist
              │              └─────────────────────────┘
              │                   medical_tools.py (TV1)
              │                           │
              └───────────┬───────────────┘
                          ▼
                  telemetry/ (logger + metrics)
                  logs/YYYY-MM-DD.log
```

---

## TV1 — Tools Engineer (BaoVu2k4)

**Files phụ trách**: `src/tools/medical_tools.py`, `src/telemetry/tool_metrics.py`

### Luồng nội bộ của TV1

```
Agent gọi _execute_tool("lookup_surgery_info", '"nhịn ăn"')
    │
    ▼
lookup_surgery_info(query)
    │
    ├── _tokenize(query)          → set token (bỏ stop words tiếng Việt)
    ├── _find_alias_keys(query)   → tìm canonical key qua _ALIASES dict (50 entries)
    │
    ├── for key, info in _KB (25 entries):
    │       _score_match(query_tokens, key)
    │           score = matched_tokens + (matched/key_len) × 0.5   ← float tiebreaker
    │           + bonus 2 nếu key nằm trong alias_keys
    │
    ├── sort by score desc → lấy top 2
    │
    ├── logger.log_event("TOOL_EXECUTED", {...})
    ├── tool_tracker.record("lookup_surgery_info", matched=True, ...)
    │
    └── return "\n\n".join(top 2 results)
```

```
Agent gọi _execute_tool("check_danger_signs", '"vết mổ đỏ và sưng"')
    │
    ▼
check_danger_signs(symptoms)
    │
    ├── for keyword in _DANGER (16 keywords, 3 severity levels):
    │       _keyword_matches_symptoms(keyword, symptoms)
    │           1 từ  → exact substring check
    │           ≥2 từ → all(w in text for w in words)   ← bug fix: tránh miss "đỏ và sưng"
    │
    ├── sort matches by severity desc: KHẨN CẤP(3) > NGUY HIỂM(2) > CHÚ Ý(1)
    │
    ├── if max_severity >= NGUY HIỂM → thêm hotline 1800 599 920
    │
    ├── logger.log_event("TOOL_EXECUTED", {...})
    ├── tool_tracker.record("check_danger_signs", matched=True, ...)
    │
    └── return formatted response
```

```
Agent gọi _execute_tool("get_checklist", '"post_surgery"')
    │
    ▼
get_checklist(stage)
    │
    ├── raw_key = stage.lower().strip()
    ├── resolved_key = _STAGE_ALIASES.get(raw_key, raw_key)
    │       "sau mổ" → "post_surgery", "pre" → "pre_surgery", ...
    │
    ├── _CHECKLIST.get(key)   → pre_surgery / post_surgery text
    │
    ├── logger.log_event("TOOL_EXECUTED", {...})
    ├── tool_tracker.record("get_checklist", matched=True, ...)
    │
    └── return checklist string (checkbox format)
```

**tool_metrics.py — metrics sau session:**
```
ToolMetricsTracker.record() ← gọi sau mỗi tool call
    │   lưu: calls, hits, misses, alias_hits, latency, scores
    ▼
ToolMetricsTracker.log_summary()
    └── logger.log_event("TOOL_SESSION_SUMMARY", {
            total_tool_calls, overall_success_rate,
            per-tool: success_rate, alias_hit_rate, latency_avg_ms, score_avg
        })
```

**2 bug TV1 đã fix:**

| Bug | Input gây lỗi | Root cause | Fix |
|-----|--------------|-----------|-----|
| Compound keyword | `"đỏ và sưng"` → không match `"đỏ sưng"` | Exact substring match | `all(w in text for w in words.split())` |
| Score tie-break | `"khi nào tắm"` → trả về thông tin ăn uống | `int` score, stable sort, `"ăn uống sau mổ"` xuất hiện trước trong dict | `float` + specificity = `matched + (matched/key_len)×0.5` |

---

## TV2 — ReAct Agent Engineer

**File phụ trách**: `src/agent/agent.py`

### Luồng ReAct Loop

```
ReActAgent.run(user_input)
    │
    ├── [1] _security_check(user_input)
    │       ├── check _INJECTION_PATTERNS (8 EN + 4 VI patterns)
    │       ├── check _UNSAFE_MEDICAL (6 patterns: kê đơn, chẩn đoán...)
    │       ├── check len > 500
    │       └── if blocked → return chuỗi cảnh báo + log "SECURITY_BLOCK"
    │
    ├── log "AGENT_START"
    │
    └── for step in range(1, max_steps+1=6):
            │
            ├── [2] llm.generate(conversation, system_prompt)
            │       system_prompt gồm:
            │       - Tool descriptions (từ TV1's TOOLS list)
            │       - Định dạng bắt buộc: Thought/Action/Observation/Final Answer
            │       - 5 quy tắc
            │       - [v2] Few-shot example (1 example để giảm PARSE_ERROR)
            │
            ├── log "AGENT_STEP" (step, llm_output, usage, latency_ms)
            │
            ├── [3] if "Final Answer:" in response:
            │       → tách nội dung sau "Final Answer:"
            │       → log "AGENT_END"
            │       → return answer   ← KẾT THÚC
            │
            ├── [4] _parse_action(response)
            │       regex: r"Action:\s*([a-zA-Z_]\w*)\(([^)]*)\)"
            │       → (tool_name, raw_args) hoặc None
            │
            ├── if parsed:
            │       _execute_tool(tool_name, raw_args)
            │           _parse_args(raw_args)  ← json.loads hoặc strip quotes fallback
            │           → tool["function"](*args)   ← gọi TV1's tool functions
            │       log "TOOL_CALL"
            │       conversation += response + f"\nObservation: {obs}\n"
            │
            └── else (PARSE_ERROR):
                    log "PARSE_ERROR"
                    conversation += response + "\n"
                    → LLM thử lại ở step tiếp theo

    → if loop kết thúc mà chưa có Final Answer:
        log "AGENT_TIMEOUT"
        return "Xin lỗi... Hotline Vinmec: 1800 599 920"
```

**v1 → v2 cải tiến:**
- v1: system prompt không có ví dụ mẫu → LLM hay sinh PARSE_ERROR
- v2: thêm `enable_few_shot=True` + 1 ví dụ đầy đủ Thought/Action/Observation/Final Answer vào cuối system prompt → giảm PARSE_ERROR

---

## TV3 — UI & Integration Engineer

**Files phụ trách**: `chatbot.py`, `app.py`, `main.py`, `tests/test_agent.py`, `frontend/`

### Luồng Chatbot Baseline (`chatbot.py`)

```
chatbot.py
    │
    ├── đọc OLLAMA_MODEL và OLLAMA_HOST từ .env
    │
    └── for query in TEST_CASES (5 câu hỏi):
            │
            ├── ollama.Client().chat(model, messages=[system, user])
            │       Backend: model cục bộ qua Ollama (không có tools)
            │       → trả lời từ training memory của model
            │
            ├── tracker.track_request(provider, model, usage, latency_ms)
            ├── logger.log_event("CHATBOT_RESPONSE", {...})
            │
            └── print(content[:200])
```

### Luồng HTTP API Server (`app.py`)

```
ThreadingHTTPServer(:8000) — ChatHandler
    │
    ├── GET /api/health     → JSON {status, model, frontend}
    │
    ├── GET /*
    │       if frontend/dist/ exists → serve static files (React build)
    │       else → render_dev_fallback() HTML hướng dẫn npm run build
    │
    └── POST /api/chat
            │
            ├── read_json_body()    → {messages: [...], model: ...}
            ├── normalize_messages() → validate role ∈ {user, assistant}
            │
            ├── OLLAMA_CLIENT.chat(model, [system_prompt, *messages])
            │       ← gọi Ollama cục bộ (KHÔNG qua ReActAgent/tools)
            │
            ├── tracker.track_request(...)
            ├── logger.log_event("CHAT_API_RESPONSE", {...})
            │
            └── JSON response {reply, model, latency_ms, usage}
```

**Lưu ý**: `app.py` của TV3 là chatbot baseline (Ollama không tools), không phải ReAct Agent. Frontend React giao tiếp với `app.py` qua `/api/chat`.

### Luồng Tests (`tests/test_agent.py`)

```
test_agent.py
    │
    ├── khởi tạo GeminiProvider + ReActAgent (dùng TV1's TOOLS)
    │
    └── for (question, keywords) in TEST_CASES (7 cases):
            answer = agent.run(question)
            ok = all(kw.lower() in answer.lower() for kw in keywords)
            print PASS/FAIL + thiếu keyword nào
```

Test cases:
| # | Câu hỏi | Keywords kiểm tra |
|---|---------|------------------|
| 1 | Nhịn ăn bao lâu? | `["6 tiếng", "nhịn"]` |
| 2 | Ngày đầu ăn gì? | `["súp", "lỏng", "nước"]` |
| 3 | Vết mổ đỏ sưng? | `["nguy hiểm", "viện", "1800"]` |
| 4 | Khi nào tắm? | `["48"]` |
| 5 | Bao giờ tái khám? | `["7", "10"]` |
| 6 | Injection test | `["không hợp lệ"]` |
| 7 | Kê đơn test | `["không thể"]` |

---

## Luồng end-to-end đầy đủ (ReAct Agent)

```
User: "Vết mổ bị đỏ và sưng, có nguy hiểm không?"
    │
    ▼ [TV2] ReActAgent.run()
    │
    ├── _security_check()  → None (không vi phạm)
    │
    └── Step 1: llm.generate()
            LLM output:
            "Thought: Bệnh nhân mô tả triệu chứng sau mổ, cần kiểm tra nguy hiểm.
             Action: check_danger_signs("vết mổ bị đỏ và sưng")"
            │
            ▼ [TV2] _parse_action() → ("check_danger_signs", '"vết mổ bị đỏ và sưng"')
            │
            ▼ [TV1] check_danger_signs("vết mổ bị đỏ và sưng")
            │   _keyword_matches_symptoms("đỏ sưng", text)
            │   → all(["đỏ","sưng"] in text) → True  ← bug đã fix
            │   → match: [("NGUY HIỂM", "Vết mổ đỏ, sưng...")]
            │   → append hotline 1800 599 920
            │   → tool_tracker.record(matched=True)
            │   → logger.log_event("TOOL_EXECUTED", {highest_severity: "NGUY HIỂM"})
            │
            ▼ Observation: "[NGUY HIỂM] Vết mổ đỏ, sưng, nóng... ⚠️ 1800 599 920"
            │
            Step 2: llm.generate()
            LLM output:
            "Thought: Đây là tình trạng nguy hiểm, hướng dẫn đến viện ngay.
             Final Answer: Vết mổ đỏ và sưng là dấu hiệu viêm nhiễm nguy hiểm.
             Hãy đến cơ sở y tế ngay hoặc gọi Vinmec: 1800 599 920 (miễn phí, 24/7)."
            │
            ▼ [TV2] "Final Answer:" detected → return answer
            │
            ▼ [TV3/TV1] tool_tracker.log_summary() → TOOL_SESSION_SUMMARY vào log

Final Answer hiển thị cho user
```

---

---

# Kiểm tra báo cáo TV1 (REPORT_TV1.md) với format đề yêu cầu

## So sánh với TEMPLATE_INDIVIDUAL_REPORT.md

### Header

| Trường | Template yêu cầu | TV1 có không |
|--------|-----------------|-------------|
| Student Name | ✓ | ✓ `BaoVu2k4` |
| **Student ID** | ✓ | **✗ THIẾU** |
| Date | ✓ | ✓ `2026-06-01` |

**Vấn đề 1**: Thiếu trường **Student ID** trong header.

---

### Phần I — Technical Contribution (15đ)

Template yêu cầu:
- Modules Implemented (tên file)
- Code Highlights (snippet hoặc line reference)
- Documentation (giải thích code tương tác với ReAct loop như thế nào)

TV1 đã làm:
- ✓ Bảng liệt kê module với dòng code và mô tả
- ✓ Code snippet chi tiết (`_score_match`, scoring formula, 3 tool functions)
- ✓ Mục 1.3 giải thích rõ luồng tương tác với ReAct loop (5 bước)

**Đánh giá**: Đạt và vượt yêu cầu. Nội dung phong phú hơn template.

---

### Phần II — Debugging Case Study (10đ)

Template yêu cầu:
- Problem Description
- **Log Source** (snippet từ `logs/YYYY-MM-DD.log`)
- Diagnosis (tại sao LLM/prompt/tool làm vậy)
- Solution (fix cụ thể)

Yêu cầu NHOM_LAM_BAI.md: **"Dán log `PARSE_ERROR`/`AGENT_TIMEOUT` thật + giải thích"**

TV1 đã làm:
- ✓ 2 bug cases (nhiều hơn yêu cầu 1)
- ✓ Có log JSON trước và sau fix
- ✓ Diagnosis rõ ràng (root cause analysis)
- ✓ Solution với code snippet

**Vấn đề 2 (quan trọng)**: NHOM_LAM_BAI.md yêu cầu log `PARSE_ERROR` hoặc `AGENT_TIMEOUT` — tức là **lỗi ở tầng agent (TV2)**, không phải lỗi tầng tool. TV1 chỉ debug `TOOL_EXECUTED` / `TOOL_NO_MATCH` — đây là **tool-level bugs, không phải agent-level bugs**. Nếu giảng viên chấm sát yêu cầu, phần II có thể bị trừ điểm.

---

### Phần III — Personal Insights: Chatbot vs ReAct (10đ)

Template yêu cầu 3 câu hỏi cụ thể:
1. Reasoning: `Thought` block giúp gì?
2. Reliability: Agent tệ hơn Chatbot khi nào?
3. Observation: Feedback loop ảnh hưởng thế nào?

Yêu cầu NHOM_LAM_BAI.md: **"Bảng so sánh chatbot vs agent từ kết quả test"**

TV1 đã làm:
- ✓ Trả lời đủ 3 câu hỏi với ví dụ cụ thể
- ✓ Có bảng so sánh (tình huống × Chatbot × Agent)
- ✓ Ví dụ thực tế từ quá trình test

**Vấn đề 3 (nhỏ)**: Bảng so sánh dựa trên phân tích định tính, không có số liệu từ kết quả chạy `test_agent.py` thực tế (pass/fail rate, latency so sánh). NHOM_LAM_BAI.md ghi rõ "từ kết quả test".

---

### Phần IV — Future Improvements (5đ)

Template yêu cầu: Scalability, Safety, Performance

TV1 đã làm:
- ✓ Scalability: Vector DB + RAG (Pinecone/Qdrant)
- ✓ Safety: Supervisor LLM + code snippet
- ✓ Performance: Async tool execution + code snippet
- ✓ **Bonus**: Observability (OpenTelemetry + Prometheus) — không có trong template nhưng là điểm cộng

**Đánh giá**: Đạt và vượt yêu cầu.

---

### Yêu cầu đặt tên file

Template note: **"Rename to `REPORT_[YOUR_NAME].md`"**

TV1 nộp file tên: `REPORT_TV1.md`

**Vấn đề 4 (nhỏ)**: File chưa đổi tên theo tên thật. Thành viên khác (`Pham_Manh_Thang`) đã đổi tên đúng format.

---

## Tóm tắt kết quả kiểm tra

| Phần | Điểm tối đa | Đánh giá | Ghi chú |
|------|------------|----------|---------|
| Header | — | ⚠️ Thiếu Student ID | |
| I. Technical Contribution | 15đ | ✅ Đạt tốt | Code snippet + interaction flow đầy đủ |
| II. Debugging Case Study | 10đ | ⚠️ Lệch yêu cầu | Debug tool-level thay vì `PARSE_ERROR`/`AGENT_TIMEOUT` như đề yêu cầu |
| III. Personal Insights | 10đ | ✅ Đạt | Có phân tích nhưng thiếu số liệu test thực tế |
| IV. Future Improvements | 5đ | ✅ Đạt tốt | 4 đề xuất, vượt yêu cầu 3 |
| Tên file | — | ⚠️ Chưa đổi tên | Nên là `REPORT_BaoVu2k4.md` |

### Điểm cần bổ sung/sửa cho REPORT_TV1.md:

1. **Bắt buộc**: Thêm `Student ID` vào header
2. **Quan trọng**: Phần II cần bổ sung phân tích 1 log `PARSE_ERROR` hoặc `AGENT_TIMEOUT` thực tế từ `logs/` — đây là yêu cầu của cả template lẫn NHOM_LAM_BAI.md
3. **Nên có**: Phần III thêm bảng số liệu từ kết quả chạy `test_agent.py` (pass rate, latency)
4. **Nhỏ**: Xem xét đổi tên file thành `REPORT_[TenThat].md`
