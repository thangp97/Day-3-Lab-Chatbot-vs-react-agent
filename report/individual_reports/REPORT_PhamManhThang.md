# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Phạm Mạnh Thắng
- **Student ID**: 2A202600921
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

Trong vai trò TV2, em phụ trách thiết kế và hoàn thiện logic cốt lõi của **ReAct Agent**, đồng thời triển khai hệ thống **Security Guardrails** nhằm đảm bảo tính an toàn và độ tin cậy cho ứng dụng AI y tế. Các phần được triển khai tập trung vào việc tối ưu vòng lặp ReAct, xử lý ngoại lệ (error handling) khi gọi công cụ, tích hợp log telemetry và sử dụng kỹ thuật few-shot prompting để giảm thiểu lỗi parse.

- **Modules Implementated**: [src/agent/agent.py](../../src/agent/agent.py)
- **Code Highlights**:
  - **Prompt Engineering & Few-shot Learning**: Thiết kế System prompt tuân thủ nghiêm ngặt định dạng ReAct (Thought-Action-Observation) kèm theo few-shot ví dụ để giảm tỷ lệ PARSE_ERROR từ LLM cục bộ (local model): [src/agent/agent.py](../../src/agent/agent.py#L45-L77).
  - **Security Guardrails**: Xây dựng màng lọc (guard) chặn hiệu quả các kỹ thuật prompt injection (jailbreak, roleplay) và từ chối các yêu cầu y tế không an toàn (chẩn đoán, kê đơn): [src/agent/agent.py](../../src/agent/agent.py#L9-L98).
  - **Robust ReAct Loop & Telemetry**: Xây dựng vòng lặp ReAct hoàn chỉnh với khả năng đo lường hiệu suất chi tiết. Tích hợp telemetry để ghi log toàn diện các sự kiện (AGENT_START/STEP/END, TOOL_CALL, PARSE_ERROR, TIMEOUT) giúp dễ dàng tracking và debug: [src/agent/agent.py](../../src/agent/agent.py#L113-L189).
  - **Dynamic Tool Execution & Error Handling**: Xử lý gọi hàm động và parsing đối số (args) an toàn, tự động khắc phục lỗi JSON formatting và ngăn chặn vòng lặp vô tận (infinite loop) khi Agent gọi trùng lặp công cụ: [src/agent/agent.py](../../src/agent/agent.py#L101-L111) và [src/agent/agent.py](../../src/agent/agent.py#L168-L200).
- **Documentation**: Kiến trúc Agent nhận input từ người dùng, thực thi bước kiểm tra bảo mật (Security Check), sau đó khởi tạo prompt ReAct. LLM sẽ suy luận (Thought), quyết định gọi công cụ (Action) và nhận kết quả (Observation). Quá trình lặp lại cho đến khi mô hình tổng hợp được câu trả lời cuối cùng (Final Answer) an toàn và chính xác.

---

## II. Debugging Case Study (10 Points)

- **Problem Description**: LLM cục bộ thường xuyên bị mắc kẹt trong vòng lặp vô hạn (infinite loop) khi gọi đi gọi lại cùng một công cụ nhiều lần, hoặc sinh ra các chuỗi văn bản không theo định dạng chuẩn, dẫn đến PARSE_ERROR và TIMEOUT.
- **Log Source**: PARSE_ERROR và TIMEOUT xuất hiện tại [logs/2026-06-01.log](../../logs/2026-06-01.log). Sự cố công cụ bị gọi lặp lại nhiều bước cũng được ghi nhận tại file log này.
- **Diagnosis**: Do sử dụng mô hình local (Phi-3/Qwen) có khả năng tuân thủ định dạng (instruction following) hạn chế hơn các mô hình thương mại lớn, mô hình gặp khó khăn trong việc dừng suy luận để chuyển sang trạng thái "Final Answer". Khi context window bị kéo dài bởi các thông tin nhiễu, biểu thức chính quy (regex) không thể trích xuất được `Action`.
- **Solution**: 
  1. Thêm chỉ thị cứng trong System Prompt: *"Sau khi có Observation, lượt kế tiếp phải trả Final Answer, không gọi tool thêm."*
  2. Triển khai cơ chế **Infinite Loop Guardrail** ở mức logic code: liên tục theo dõi `last_call`, nếu phát hiện `current_call == last_call` quá 1 lần, hệ thống sẽ short-circuit và ép model trả về kết quả bằng một bản tóm tắt nhanh từ `observation` trước đó. Tham chiếu: [src/agent/agent.py](../../src/agent/agent.py#L162-L181).

**Bằng chứng bổ sung về Bảo mật**: Các nỗ lực tấn công "jailbreak" hoặc ép mô hình đóng vai bác sĩ kê đơn đã bị chặn thành công, ghi nhận bằng sự kiện `SECURITY_BLOCK`.

---

## III. Personal Insights: Chatbot vs ReAct Agent (10 Points)

Qua quá trình phát triển hệ thống, em rút ra các điểm khác biệt cốt lõi:

1. **Khả năng Lập luận (Reasoning vs Retrieval)**: Cơ chế "Thought" giúp Agent tự đánh giá mức độ hiểu biết của mình và quyết định xem có cần sử dụng công cụ bổ trợ hay không. Điều này làm giảm triệt để hiện tượng ảo giác (hallucination) vì câu trả lời được neo (anchor) vào dữ liệu thực tế từ công cụ. Ngược lại, Chatbot baseline chỉ phụ thuộc vào kiến thức nội tại hoặc một pipeline RAG tĩnh, thiếu đi bước tự phản tỉnh (self-reflection).
2. **Độ tin cậy và Đánh đổi (Reliability Trade-offs)**: Dù thông minh hơn, Agent lại mong manh hơn Chatbot truyền thống. Nếu LLM không tuân thủ định dạng ReAct, toàn bộ pipeline có thể đổ vỡ (PARSE_ERROR). Hệ thống Agent cũng yêu cầu độ trễ (latency) cao hơn do phải thực hiện nhiều lời gọi API (multi-step calls) cho một truy vấn duy nhất.
3. **Tính Phản ứng và Ngữ cảnh (Observation Loop)**: Observation đóng vai trò là cơ chế phản hồi (feedback loop) thời gian thực. Nhờ đó, Agent có thể xử lý các tình huống phân nhánh, chẳng hạn như khi hệ thống phát hiện triệu chứng nguy hiểm từ tool `check_danger_signs`, Agent sẽ linh hoạt chuyển hướng kịch bản để yêu cầu cung cấp đường dây nóng (hotline) cấp cứu.

---

## IV. Future Improvements (5 Points)

Để đưa hệ thống lên mức sẵn sàng cho môi trường Production, em đề xuất các cải tiến sau:

- **Scalability & Routing**: Xây dựng kiến trúc Semantic Router để phân loại ý định người dùng (intent classification) trước khi gọi Agent. Nếu câu hỏi đơn giản (chitchat), có thể chuyển cho Chatbot thông thường để tiết kiệm chi phí và độ trễ.
- **Safety & Compliance**: Tích hợp một LLM "Supervisor" nhỏ và nhanh để đánh giá nội dung đầu ra (output validation) lần cuối trước khi hiển thị cho bệnh nhân, đảm bảo không có bất kỳ lời khuyên y tế sai lệch nào lọt ra ngoài. Thêm allowlist/schema validation bằng Pydantic cho các tham số công cụ.
- **Asynchronous Execution & Streaming**: Tách việc thực thi công cụ sang Message Queue (ví dụ: Celery/Redis) để xử lý bất đồng bộ. Implement cơ chế Streaming UI để liên tục cập nhật trạng thái suy nghĩ (Thinking...) của Agent, giúp cải thiện trải nghiệm người dùng trong lúc chờ đợi các truy vấn có độ trễ cao.

---

> [!NOTE]
> Toàn bộ quá trình thực thi và log lỗi đã được tự động ghi lại tại thư mục `logs/` trong hệ thống.
