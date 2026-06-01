# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Pham Manh Thang
- **Student ID**: [Chua cung cap]
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

Trong vai tro TV2, em phu trach hoan thien ReAct Agent va security guard. Cac phan duoc trien khai tap trung vao agent loop, parsing Action/args, log telemetry, va giam parse error bang few-shot.

- **Modules Implementated**: [src/agent/agent.py](src/agent/agent.py#L1-L200)
- **Code Highlights**:
	- System prompt ReAct + quy tac + few-shot vi du de giam PARSE_ERROR: [src/agent/agent.py](src/agent/agent.py#L45-L77)
	- Security guard chan prompt injection va yeu cau y te khong an toan: [src/agent/agent.py](src/agent/agent.py#L9-L98)
	- Vong lap ReAct day du + telemetry (AGENT_START/STEP/END, TOOL_CALL, PARSE_ERROR, TIMEOUT): [src/agent/agent.py](src/agent/agent.py#L113-L189)
	- Tool execution dong va parsing args an toan: [src/agent/agent.py](src/agent/agent.py#L101-L111) va [src/agent/agent.py](src/agent/agent.py#L168-L200)
- **Documentation**: Agent nhan input nguoi dung, tao prompt ReAct, goi LLM, parse Action de goi tool, ghi Observation vao conversation, lap den khi co Final Answer. Guard chay truoc LLM de ngan prompt injection va yeu cau chuan doan/ke don.

---

## II. Debugging Case Study (10 Points)

- **Problem Description**: Model local lap lai tool call nhieu lan va co output rac o buoc cuoi, dan den PARSE_ERROR va TIMEOUT.
- **Log Source**: PARSE_ERROR va TIMEOUT xuat hien tai [logs/2026-06-01.log](logs/2026-06-01.log#L17-L19). Tool bi lap lai nhieu buoc tai [logs/2026-06-01.log](logs/2026-06-01.log#L2-L16).
- **Diagnosis**: Prompt ReAct chua du manh voi model local, dan den viec khong chiu ket thuc bang Final Answer va lap tool call. Khi output bi nhieu, regex khong parse duoc Action.
- **Solution**: Them quy tac “sau Observation phai tra Final Answer”, them few-shot, va guardrail dung som neu tool bi lap. Tham chieu: [src/agent/agent.py](src/agent/agent.py#L45-L181).

**Bang chung bổ sung (security guard)**: cac cau injection va yeu cau ke don bi chan voi event SECURITY_BLOCK trong [logs/2026-06-01.log](logs/2026-06-01.log#L28-L29).

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
> Log da duoc thu thap trong [logs/2026-06-01.log](logs/2026-06-01.log).
