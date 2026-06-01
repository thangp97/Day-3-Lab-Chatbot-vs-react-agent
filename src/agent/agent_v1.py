"""
Agent v1 — Basic ReAct loop without improvements.
Baseline for comparison with Agent v2 (agent.py).

Key differences from v2:
- No security check (prompt injection / unsafe medical)
- Simpler English system prompt with no few-shot examples
- No repeat action detection (can loop all the way to max_steps)
- No AgentTokenTracker integration; exposes raw step counts via attributes
"""

import json
import re
from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger


class ReActAgentV1:
    """Basic ReAct loop: Thought → Action → Observation → Final Answer."""

    def __init__(self, llm: LLMProvider, tools: list, max_steps: int = 6):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self._last_prompt_tokens: int = 0
        self._last_completion_tokens: int = 0
        self._last_steps: int = 0

    def _system_prompt(self) -> str:
        tool_list = "\n".join(f"- {t['name']}: {t['description']}" for t in self.tools)
        return (
            "You are VinmecBot, a hospital assistant for Vinmec hospital.\n"
            "Answer patient questions about laparoscopic appendectomy surgery in Vietnamese.\n\n"
            "TOOLS:\n"
            f"{tool_list}\n\n"
            "REQUIRED FORMAT:\n"
            "Thought: [reasoning]\n"
            'Action: tool_name("argument")\n'
            "Observation: [tool result — filled by system]\n"
            "Final Answer: [complete answer in Vietnamese]\n\n"
            "RULES:\n"
            "1. Only use listed tools.\n"
            "2. Always end with 'Final Answer:'.\n"
        )

    def _parse_action(self, text: str):
        match = re.search(r"Action:\s*([a-zA-Z_]\w*)\(([^)]*)\)", text)
        if not match:
            return None
        return match.group(1).strip(), match.group(2).strip()

    def _parse_args(self, raw_args: str) -> list:
        try:
            return json.loads(f"[{raw_args}]")
        except Exception:
            return [raw_args.strip().strip('"').strip("'")]

    def _execute_tool(self, tool_name: str, raw_args: str) -> str:
        for tool in self.tools:
            if tool["name"] == tool_name:
                try:
                    return tool["function"](*self._parse_args(raw_args))
                except Exception as exc:
                    return f"Error calling {tool_name}: {exc}"
        return f"Tool '{tool_name}' not found. Available: {[t['name'] for t in self.tools]}"

    def run(self, user_input: str) -> str:
        """Run the basic ReAct loop (no security check, no repeat detection)."""
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0
        self._last_steps = 0

        logger.log_event("AGENT_START", {
            "input": user_input,
            "model": self.llm.model_name,
            "version": "v1",
        })

        conversation = f"User: {user_input}\n"

        for step in range(1, self.max_steps + 1):
            self._last_steps = step
            result = self.llm.generate(conversation, system_prompt=self._system_prompt())
            response = result.get("content", "")
            usage = result.get("usage") or {}
            self._last_prompt_tokens += usage.get("prompt_tokens", 0)
            self._last_completion_tokens += usage.get("completion_tokens", 0)

            logger.log_event("AGENT_STEP", {
                "step": step,
                "version": "v1",
                "llm_output": response[:300],
                "usage": usage,
                "latency_ms": result.get("latency_ms", 0),
            })

            if "Final Answer:" in response:
                answer = response.split("Final Answer:")[-1].strip()
                logger.log_event("AGENT_END", {
                    "steps": step,
                    "answer": answer[:120],
                    "version": "v1",
                })
                return answer

            parsed = self._parse_action(response)
            if parsed:
                tool_name, raw_args = parsed
                observation = self._execute_tool(tool_name, raw_args)
                logger.log_event("TOOL_CALL", {
                    "step": step,
                    "tool": tool_name,
                    "args": raw_args,
                    "version": "v1",
                })
                conversation += response + f"\nObservation: {observation}\n"
                continue

            logger.log_event("PARSE_ERROR", {
                "step": step,
                "version": "v1",
                "response": response[:200],
            })
            conversation += response + "\n"

        logger.log_event("AGENT_TIMEOUT", {"max_steps": self.max_steps, "version": "v1"})
        return "Xin lỗi, không tìm được câu trả lời. Hotline Vinmec: 1800 599 920."
