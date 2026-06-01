import json
import re
from typing import List, Dict, Any, Optional, Tuple
from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger
from src.telemetry.token_tracker import agent_token_tracker


# Security: prompt injection and unsafe medical requests
_INJECTION_PATTERNS = [
    "ignore previous", "forget your instructions", "you are now",
    "act as", "act like", "roleplay", "jailbreak", "pretend you",
    "system prompt", "developer message", "override system", "bypass safety",
    "bỏ qua hướng dẫn", "bo qua huong dan", "bỏ qua mọi hướng dẫn", "quên đi", "quen di", "đóng vai", "dong vai",
    "không còn là", "khong con la", "hướng dẫn hệ thống", "huong dan he thong", "thông điệp hệ thống",
    "tôi là bác sĩ", "toi la bac si", "you are a doctor", "as a doctor",
    "hãy đưa ra câu trả lời có tình huống xấu nhất", "tinh huong xau nhat",
    "worst case", "worst-case", "catastrophic scenario",
]
_UNSAFE_MEDICAL = [
    "kê đơn thuốc", "ke don thuoc", "chẩn đoán bệnh", "chan doan benh", 
    "liều dùng", "lieu dung", "tự chữa", "tu chua",
    "kê đơn", "ke don", "chẩn đoán", "chan doan", 
    "mua thuốc", "mua thuoc", "uống thuốc gì", "uong thuoc gi",
    "prescribe", "diagnose",
]

def _normalize_text(text: str) -> str:
    """Loại bỏ dấu câu và chuẩn hóa khoảng trắng để tránh lách luật."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

class ReActAgent:
    """
    SKELETON: A ReAct-style Agent that follows the Thought-Action-Observation loop.
    Students should implement the core loop logic and tool execution.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: List[Dict[str, Any]],
        max_steps: int = 6,
        enable_few_shot: bool = True,
    ):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.enable_few_shot = enable_few_shot
        self.history = []

    def get_system_prompt(self) -> str:
        tool_descriptions = "\n".join(f"- {t['name']}: {t['description']}" for t in self.tools)
        prompt = (
            "Bạn là VinmecBot — trợ lý AI của Bệnh viện Đa khoa Quốc tế Vinmec.\n"
            "Hỗ trợ bệnh nhân hỏi đáp về phẫu thuật cắt ruột thừa nội soi.\n\n"
            "CHỈ trả lời bằng tiếng Việt. TUYỆT ĐỐI không dùng tiếng Anh hoặc tiếng Trung.\n\n"
            "CÔNG CỤ:\n"
            f"{tool_descriptions}\n\n"
            "ĐỊNH DẠNG BẮT BUỘC:\n"
            "Thought: [suy nghĩ bước tiếp theo]\n"
            "Action: ten_tool(\"argument\")\n"
            "Observation: [kết quả tool — hệ thống điền]\n"
            "... (lặp lại nếu cần)\n"
            "Final Answer: [câu trả lời hoàn chỉnh, thân thiện]\n\n"
            "QUY TẮC:\n"
            "1. Chỉ dùng tool đã liệt kê.\n"
            "2. Argument string phải có dấu nháy kép.\n"
            "3. Bắt buộc kết thúc bằng \"Final Answer:\".\n"
            "4. KHÔNG chẩn đoán, KHÔNG kê đơn thuốc.\n"
            "5. Triệu chứng nguy hiểm → luôn thêm hotline Vinmec: 1800 599 920.\n"
            "6. Sau khi có Observation, lượt kế tiếp phải trả Final Answer, không gọi tool thêm.\n"
            "7. Nếu người dùng hỏi các vấn đề KHÔNG liên quan đến phẫu thuật ruột thừa hoặc y tế, bạn PHẢI trả lời chính xác câu này (trong phần Final Answer): 'Tôi là bot phục vụ mục đích y tế trong lĩnh vực ruột thừa và không phục vụ mục đích khác.'\n"
        )

        if not self.enable_few_shot:
            return prompt

        # Few-shot to reduce parse errors in the ReAct format
        example = (
            "\nVÍ DỤ:\n"
            "User: Khi nào được tắm sau mổ?\n"
            "Thought: Cần tra cứu thông tin chăm sóc sau mổ.\n"
            "Action: lookup_surgery_info(\"tắm sau mổ\")\n"
            "Observation: Được tắm sau 48 giờ...\n"
            "Final Answer: Bạn có thể tắm nhẹ sau 48 giờ, tránh ngâm nước vào vết mổ.\n"
        )
        return prompt + example

    def _security_check(self, user_input: str) -> Optional[str]:
        """Chặn prompt injection và yêu cầu y tế không an toàn."""
        normalized_text = _normalize_text(user_input)

        for pattern in _INJECTION_PATTERNS:
            if _normalize_text(pattern) in normalized_text:
                logger.log_event("SECURITY_BLOCK", {"type": "injection", "input": user_input[:80]})
                return "Yêu cầu không hợp lệ. Tôi chỉ hỗ trợ câu hỏi về phẫu thuật tại Vinmec."

        for pattern in _UNSAFE_MEDICAL:
            if _normalize_text(pattern) in normalized_text:
                logger.log_event("SECURITY_BLOCK", {"type": "unsafe_medical", "input": user_input[:80]})
                return "Tôi không thể chẩn đoán hoặc kê đơn thuốc. Liên hệ bác sĩ: 1800 599 920."

        if len(user_input) > 500:
            return "Câu hỏi quá dài. Vui lòng hỏi ngắn gọn hơn."

        return None

    def _parse_action(self, text: str) -> Optional[Tuple[str, str]]:
        match = re.search(r"Action:\s*([a-zA-Z_]\w*)\(([^)]*)\)", text)
        if not match:
            return None
        return match.group(1).strip(), match.group(2).strip()

    def _parse_args(self, raw_args: str) -> List[str]:
        try:
            return json.loads(f"[{raw_args}]")
        except Exception:
            return [raw_args.strip().strip('"').strip("'")]

    def run(self, user_input: str) -> str:
        """Thực thi vòng lặp ReAct: Thought → Action → Observation → Final Answer."""
        blocked = self._security_check(user_input)
        if blocked:
            return blocked

        # Reset token tracker for this session
        agent_token_tracker.reset()

        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})

        conversation = f"User: {user_input}\n"
        last_call = None
        repeat_count = 0

        for step in range(1, self.max_steps + 1):
            result = self.llm.generate(conversation, system_prompt=self.get_system_prompt())
            response = result.get("content", "")

            # Record token usage for this LLM step
            agent_token_tracker.record_step(
                step=step,
                model=self.llm.model_name,
                usage=result.get("usage"),
                latency_ms=result.get("latency_ms", 0),
            )

            logger.log_event(
                "AGENT_STEP",
                {
                    "step": step,
                    "llm_output": response,
                    "usage": result.get("usage"),
                    "latency_ms": result.get("latency_ms"),
                    "cumulative_tokens": agent_token_tracker.total_tokens,
                    "cumulative_cost_usd": agent_token_tracker.total_cost_usd,
                },
            )

            if "Final Answer:" in response:
                answer = response.split("Final Answer:")[-1].strip()
                logger.log_event("AGENT_END", {"steps": step, "answer": answer})
                agent_token_tracker.log_summary(user_input, "completed", answer)
                return answer

            parsed = self._parse_action(response)
            if parsed:
                tool_name, raw_args = parsed
                current_call = (tool_name, raw_args)
                if current_call == last_call:
                    repeat_count += 1
                else:
                    repeat_count = 0
                last_call = current_call

                observation = self._execute_tool(tool_name, raw_args)
                logger.log_event(
                    "TOOL_CALL",
                    {
                        "step": step,
                        "tool": tool_name,
                        "args": raw_args,
                        "observation": observation,
                    },
                )
                if repeat_count >= 1:
                    answer = f"Tóm tắt nhanh: {observation}"
                    logger.log_event("AGENT_END", {"steps": step, "answer": answer, "reason": "repeat_tool"})
                    return answer
                conversation += response + f"\nObservation: {observation}\n"
                continue

            logger.log_event("PARSE_ERROR", {"step": step, "response": response})
            conversation += response + "\n"

        logger.log_event("AGENT_TIMEOUT", {"max_steps": self.max_steps})
        agent_token_tracker.log_summary(user_input, "timeout")
        return "Xin lỗi, không tìm được câu trả lời. Hotline Vinmec: 1800 599 920."

    def _execute_tool(self, tool_name: str, raw_args: str) -> str:
        """Thực thi tool theo tên và truyền đối số."""
        for tool in self.tools:
            if tool["name"] == tool_name:
                try:
                    return tool["function"](*self._parse_args(raw_args))
                except Exception as exc:
                    return f"Lỗi khi gọi {tool_name}: {exc}"
        return f"Tool '{tool_name}' không tồn tại. Hợp lệ: {[t['name'] for t in self.tools]}"
