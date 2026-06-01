# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Pham Manh Thang
- **Student ID**: [Chua cung cap]
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

Trong vai tro TV2, em phu trach hoan thien ReAct Agent va security guard. Cac phan duoc trien khai tap trung vao agent loop, parsing Action/args, log telemetry, va giam parse error bang few-shot.

- **Modules Implementated**: [src/agent/agent.py](src/agent/agent.py#L1-L164)
- **Code Highlights**:
	- System prompt ReAct + quy tac + few-shot vi du de giam PARSE_ERROR: [src/agent/agent.py](src/agent/agent.py#L39-L72)
	- Security guard chan prompt injection va yeu cau y te khong an toan: [src/agent/agent.py](src/agent/agent.py#L8-L91)
	- Vong lap ReAct day du + telemetry (AGENT_START/STEP/END, TOOL_CALL, PARSE_ERROR, TIMEOUT): [src/agent/agent.py](src/agent/agent.py#L105-L154)
	- Tool execution dong va parsing args an toan: [src/agent/agent.py](src/agent/agent.py#L93-L104) va [src/agent/agent.py](src/agent/agent.py#L156-L164)
- **Documentation**: Agent nhan input nguoi dung, tao prompt ReAct, goi LLM, parse Action de goi tool, ghi Observation vao conversation, lap den khi co Final Answer. Guard chay truoc LLM de ngan prompt injection va yeu cau chuan doan/ke don.

---

## II. Debugging Case Study (10 Points)

*Phan nay can co log that sau khi chay agent. Hien tai chua co log trong thu muc logs, vi chua thuc thi main/test.*

- **Problem Description**: LLM doi luc tra ve doan van ban khong dung format ReAct (thieu Action hoac Final Answer), dan den PARSE_ERROR va agent tiep tuc vong lap.
- **Log Source**: Chua co. Sau khi chay `python main.py`, log se nam trong `logs/YYYY-MM-DD.log` va co event `PARSE_ERROR`.
- **Diagnosis**: Nguyen nhan thuong do prompt chua du rang buoc dinh dang hoac model local khong quen format Thought/Action/Observation.
- **Solution**: Bo sung few-shot vi du trong system prompt de dinh hinh output, va giu regex parse Action on dinh. Tham chieu: [src/agent/agent.py](src/agent/agent.py#L39-L72) va [src/agent/agent.py](src/agent/agent.py#L93-L104).

*Ke hoach tai hien va cap nhat log:* chay `python main.py`, loc event `PARSE_ERROR` tu file log, dan vao day (hoac chen 1 doan JSON log ngan). Khi co log that, em se cap nhat muc Log Source va bo sung bang chung cu the.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

1. **Reasoning**: Thought giup agent tu nhan biet can dung tool hay tra loi truc tiep, giam hallucination va gan ket voi nguon thong tin trong tool. Chatbot baseline khong co buoc suy nghi va khong co co che goi tool.
2. **Reliability**: Agent co the te hon chatbot neu model khong tuan thu format ReAct (PARSE_ERROR, TIMEOUT). Khi parse loi, agent co the lap nhieu buoc va tra loi cham hon.
3. **Observation**: Observation la “feedback” tu tool, buoc tiep theo se dua tren thong tin cu the (vi du: trieu chung nguy hiem thi them hotline). Dieu nay tang tinh nhat quan so voi chatbot tra loi tu bo nho mo hinh.

---

## IV. Future Improvements (5 Points)

- **Scalability**: Tach tool execution sang hang doi (queue) de xu ly bat dong bo va gioi han timeout cho tung tool.
- **Safety**: Them “Supervisor” kiem tra dau ra truoc khi tra loi cuoi, va them allowlist cho tool arguments.
- **Performance**: Neu co nhieu tool, them bo chon tool tu dong (tool router) hoac vector DB de tim tool phu hop nhanh hon.

---

> [!NOTE]
> Bao cao se duoc cap nhat them log that sau khi chay agent va lay du lieu tu `logs/`.
