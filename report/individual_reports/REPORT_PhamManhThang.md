# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Phạm Mạnh Thắng
- **Student ID**: 2A202600921
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

Trong vai trò TV2, em phụ trách hoàn thiện ReAct Agent và security guard. Các phần được triển khai tập trung vào agent loop, parsing Action/args, log telemetry, và giảm parse error bằng few-shot.

- **Modules Implementated**: [src/agent/agent.py](src/agent/agent.py#L1-L200)
- **Code Highlights**:
	- System prompt ReAct + quy tắc + few-shot ví dụ để giảm PARSE_ERROR: [src/agent/agent.py](src/agent/agent.py#L45-L77)
	- Security guard chặn prompt injection và yêu cầu y tế không an toàn: [src/agent/agent.py](src/agent/agent.py#L9-L98)
	- Vòng lặp ReAct đầy đủ + telemetry (AGENT_START/STEP/END, TOOL_CALL, PARSE_ERROR, TIMEOUT): [src/agent/agent.py](src/agent/agent.py#L113-L189)
	- Tool execution động và parsing args an toàn: [src/agent/agent.py](src/agent/agent.py#L101-L111) và [src/agent/agent.py](src/agent/agent.py#L168-L200)
- **Documentation**: Agent nhận input người dùng, tạo prompt ReAct, gọi LLM, parse Action để gọi tool, ghi Observation vào conversation, lặp đến khi có Final Answer. Guard chạy trước LLM để ngăn prompt injection và yêu cầu chẩn đoán/kê đơn.

---

## II. Debugging Case Study (10 Points)

- **Problem Description**: Model local lặp lại tool call nhiều lần và có output rác ở bước cuối, dẫn đến PARSE_ERROR và TIMEOUT.
- **Log Source**: PARSE_ERROR và TIMEOUT xuất hiện tại [logs/2026-06-01.log](logs/2026-06-01.log#L17-L19). Tool bị lặp lại nhiều bước tại [logs/2026-06-01.log](logs/2026-06-01.log#L2-L16).
- **Diagnosis**: Prompt ReAct chưa đủ mạnh với model local, dẫn đến việc không chịu kết thúc bằng Final Answer và lặp tool call. Khi output bị nhiễu, regex không parse được Action.
- **Solution**: Thêm quy tắc “sau Observation phải trả Final Answer”, thêm few-shot, và guardrail dừng sớm nếu tool bị lặp. Tham chiếu: [src/agent/agent.py](src/agent/agent.py#L45-L181).

**Bằng chứng bổ sung (security guard)**: các câu injection và yêu cầu kê đơn bị chặn với event SECURITY_BLOCK trong [logs/2026-06-01.log](logs/2026-06-01.log#L28-L29).

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

1. **Reasoning**: Thought giúp agent tự nhận biết cần dùng tool hay trả lời trực tiếp, giảm hallucination và gắn kết với nguồn thông tin trong tool. Chatbot baseline không có bước suy nghĩ và không có cơ chế gọi tool.
2. **Reliability**: Agent có thể tệ hơn chatbot nếu model không tuân thủ format ReAct (PARSE_ERROR, TIMEOUT). Khi parse lỗi, agent có thể lặp nhiều bước và trả lời chậm hơn.
3. **Observation**: Observation là “feedback” từ tool, bước tiếp theo sẽ dựa trên thông tin cụ thể (ví dụ: triệu chứng nguy hiểm thì thêm hotline). Điều này tăng tính nhất quán so với chatbot trả lời từ bộ nhớ mô hình.

---

## IV. Future Improvements (5 Points)

- **Scalability**: Tách tool execution sang hàng đợi (queue) để xử lý bất đồng bộ và giới hạn timeout cho từng tool.
- **Safety**: Thêm “Supervisor” kiểm tra đầu ra trước khi trả lời cuối, và thêm allowlist cho tool arguments.
- **Performance**: Nếu có nhiều tool, thêm bộ chọn tool tự động (tool router) hoặc vector DB để tìm tool phù hợp nhanh hơn.

---

> [!NOTE]
> Log đã được thu thập trong [logs/2026-06-01.log](logs/2026-06-01.log).
