# Individual Report — Lab 3: Chatbot vs ReAct Agent

- **Student Name**: [Tên thành viên 3]
- **Student ID**: [MSSV]
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

### Modules Implemented

| File / Task | Thời gian (Giờ) | Mô tả ngắn gọn đóng góp |
|:------------|:---------------:|:------------------------|
| **Setup repo & Workspace** | 0.5 | Khởi tạo repo GitHub, clone dự án, thiết lập cấu trúc thư mục và cấu hình file `.env`. |
| [chatbot.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/chatbot.py) + [main.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/main.py) | 0.5 | Viết mã nguồn cho chatbot baseline chạy trực tiếp với Ollama (không dùng tools) và CLI entrypoint. |
| [app.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/app.py) | 2.5 | Hiện thực backend API server xử lý các API `/api/health`, `/api/chat` (chạy Chatbot hoặc ReAct Agent) và `/api/evaluation`. |
| [tests/test_agent.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/tests/test_agent.py) | 1.0 | Viết mã nguồn kiểm thử tự động (`pytest`) cho ReAct Agent (chặn prompt injection, chạy giả lập tool, và kiểm soát số bước tối đa). |
| **Báo cáo nhóm & Cá nhân** | 0.5 | Phối hợp làm Group Report và hoàn thành báo cáo cá nhân `REPORT_TV3.md`. |

---

### Mô tả đóng góp chính:
- **Setup & Baseline**: Chuẩn bị dự án và hoàn thiện [chatbot.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/chatbot.py) để có nền tảng so sánh hiệu năng với ReAct Agent.
- **Backend API Server**: Xây dựng [app.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/app.py) để phục vụ giao diện chat frontend, phân phối yêu cầu y tế của người dùng và hỗ trợ chạy đánh giá song song.
- **Unit Tests**: Viết kiểm thử tự động trong [test_agent.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/tests/test_agent.py) để đảm bảo Agent chặn được prompt injection độc hại và tự động dừng (hiển thị hotline) khi gặp lỗi vòng lặp vô hạn.

---

## II. Debugging Case Study (10 Points)

- **Vấn đề**: API Server [app.py](file:///d:/VinUni/Day-3-Lab-Chatbot-vs-react-agent/app.py) ghi nhận lượng token tiêu thụ bằng 0 cho chế độ Chatbot.
- **Nguyên nhân**: Hàm xử lý trong `app.py` cố gắng đọc trường `usage` từ API response của Ollama, nhưng Ollama trả trực tiếp metrics `prompt_eval_count` và `eval_count` ở cấp ngoài cùng của response.
- **Giải pháp**: Cập nhật lại cách parse dữ liệu: đọc trực tiếp hai trường trên từ response của Ollama thay vì tìm trong `usage`.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

1. **Reasoning**: Khối `Thought` giúp ReAct Agent xác định rõ ràng mục tiêu và lập kế hoạch sử dụng các công cụ y tế để lấy thông tin chính xác, hạn chế hiện tượng bịa đặt thông tin (hallucination) so với Chatbot baseline.
2. **Reliability**: ReAct Agent phản hồi chậm hơn Chatbot (do phải gọi LLM nhiều lần qua các bước). Ngoài ra, nếu mô hình local nhỏ gặp lỗi định dạng (`PARSE_ERROR`), Agent có thể bị kẹt hoặc phản hồi sai lệch.
3. **Observation**: Phản hồi từ môi trường (Observation) giúp Agent thay đổi hướng giải quyết linh hoạt. Khi công cụ cảnh báo dấu hiệu nguy kịch, Agent lập tức chuyển sang hướng khuyên bệnh nhân đi cấp cứu và cung cấp hotline.

---

## IV. Future Improvements (5 Points)

- **Scalability**: Chuyển API server sang FastAPI để hỗ trợ xử lý bất đồng bộ (`asyncio`), tăng khả năng phục vụ đồng thời.
- **Performance**: Hỗ trợ xuất dữ liệu dạng luồng (Streaming output) cho khối `Thought` và `Final Answer` để giảm thời gian chờ đợi của người dùng.
- **Self-Correction**: Thêm cơ chế tự động gửi thông báo nhắc nhở LLM sửa định dạng khi phát hiện lỗi cú pháp ReAct nhằm giảm thiểu `PARSE_ERROR`.
