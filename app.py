"""Backend API for the React chat UI."""

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import time

import ollama
from dotenv import load_dotenv

from src.agent.agent import ReActAgent
from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker
from src.tools.medical_tools import TOOLS

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

SYSTEM_PROMPT = (
	"Bạn là trợ lý bệnh viện hữu ích. Hãy trả lời rõ ràng, ngắn gọn, an toàn và CHỈ dùng tiếng Việt. "
	"Tuyệt đối không dùng tiếng Anh hoặc tiếng Trung. "
	"Nếu người dùng hỏi về triệu chứng nguy cấp, hãy khuyên họ đi khám hoặc tìm hỗ trợ y tế ngay."
)


def resolve_ollama_model() -> str:
	model_name = os.getenv("OLLAMA_MODEL")
	if not model_name:
		raise RuntimeError("Missing OLLAMA_MODEL in .env")
	return model_name.strip()


def create_ollama_client() -> ollama.Client:
	host = os.getenv("OLLAMA_HOST")
	return ollama.Client(host=host) if host else ollama.Client()


OLLAMA_MODEL = resolve_ollama_model()
OLLAMA_CLIENT = create_ollama_client()

EVALUATION_PROMPTS = [
	"Tôi cần nhịn ăn bao lâu trước phẫu thuật?",
	"Sau mổ bao lâu thì được tắm?",
	"Vết mổ đỏ và sưng thì có nguy hiểm không?",
	"Tôi có thể ăn gì vào ngày đầu sau mổ?",
	"Khi nào cần tái khám sau phẫu thuật?",
]


class OllamaProvider(LLMProvider):
	def __init__(self, model_name: str, client: ollama.Client):
		super().__init__(model_name=model_name)
		self.client = client

	def generate(self, prompt: str, system_prompt: str | None = None) -> dict:
		start_time = time.time()
		messages = []
		if system_prompt:
			messages.append({"role": "system", "content": system_prompt})
		messages.append({"role": "user", "content": prompt})

		response = self.client.chat(model=self.model_name, messages=messages)
		latency_ms = int((time.time() - start_time) * 1000)
		content = response.get("message", {}).get("content", "").strip()
		usage = response.get("usage", {})
		usage_payload = {
			"prompt_tokens": usage.get("prompt_tokens", 0),
			"completion_tokens": usage.get("completion_tokens", 0),
			"total_tokens": usage.get("total_tokens", 0),
		}

		return {
			"content": content,
			"usage": usage_payload,
			"latency_ms": latency_ms,
			"provider": "ollama",
		}

	def stream(self, prompt: str, system_prompt: str | None = None):
		raise NotImplementedError("Streaming is not implemented for OllamaProvider")


def should_use_agent(payload: dict) -> bool:
	flag = str(os.getenv("USE_AGENT", "")).strip().lower()
	use_agent_env = flag in {"1", "true", "yes", "y", "on"}
	use_agent_payload = str(payload.get("mode", "")).strip().lower() == "agent"
	return use_agent_env or use_agent_payload


def run_llm_response(model: str, prompt: str) -> tuple[str, dict, int]:
	start_time = time.time()
	response = OLLAMA_CLIENT.chat(
		model=model,
		messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
	)
	latency_ms = int((time.time() - start_time) * 1000)
	content = response.get("message", {}).get("content", "").strip()
	usage = response.get("usage", {})
	usage_payload = {
		"prompt_tokens": usage.get("prompt_tokens", 0),
		"completion_tokens": usage.get("completion_tokens", 0),
		"total_tokens": usage.get("total_tokens", 0),
	}
	return content, usage_payload, latency_ms


def run_agent_response(model: str, prompt: str) -> tuple[str, dict, int]:
	start_time = time.time()
	provider = OllamaProvider(model_name=model, client=OLLAMA_CLIENT)
	agent = ReActAgent(llm=provider, tools=TOOLS)
	content = agent.run(prompt)
	latency_ms = int((time.time() - start_time) * 1000)
	usage_payload = {
		"prompt_tokens": 0,
		"completion_tokens": 0,
		"total_tokens": 0,
	}
	return content, usage_payload, latency_ms


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
	body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
	handler.send_response(status)
	handler.send_header("Content-Type", "application/json; charset=utf-8")
	handler.send_header("Content-Length", str(len(body)))
	handler.end_headers()
	handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
	payload = body.encode("utf-8")
	handler.send_response(status)
	handler.send_header("Content-Type", "text/html; charset=utf-8")
	handler.send_header("Content-Length", str(len(payload)))
	handler.end_headers()
	handler.wfile.write(payload)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
	content_length = int(handler.headers.get("Content-Length", "0"))
	raw_body = handler.rfile.read(content_length) if content_length else b"{}"
	try:
		return json.loads(raw_body.decode("utf-8"))
	except json.JSONDecodeError as exc:
		raise ValueError("Request body must be valid JSON") from exc


def normalize_messages(messages: object) -> list[dict[str, str]]:
	if not isinstance(messages, list) or not messages:
		raise ValueError("'messages' must be a non-empty list")

	normalized: list[dict[str, str]] = []
	for message in messages:
		if not isinstance(message, dict):
			continue

		role = str(message.get("role", "")).strip()
		content = str(message.get("content", "")).strip()
		if role not in {"user", "assistant"} or not content:
			continue

		normalized.append({"role": role, "content": content})

	if not normalized:
		raise ValueError("No valid user or assistant messages were provided")

	return normalized


def serve_static_file(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
	content_type, _ = mimetypes.guess_type(file_path.name)
	payload = file_path.read_bytes()
	handler.send_response(HTTPStatus.OK)
	handler.send_header("Content-Type", content_type or "application/octet-stream")
	handler.send_header("Content-Length", str(len(payload)))
	handler.end_headers()
	handler.wfile.write(payload)


def render_dev_fallback() -> str:
	return f"""<!doctype html>
<html lang=\"en\">
<html lang="vi">
  <head>
	<meta charset=\"utf-8\" />
	<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
	<title>VinMec MedChat</title>
	<style>
	  body {{
		margin: 0;
		min-height: 100vh;
		display: grid;
		place-items: center;
		background: #07111f;
		color: #f5f7ff;
		font-family: Inter, system-ui, sans-serif;
	  }}
	  main {{
		width: min(720px, calc(100vw - 32px));
		padding: 28px;
		border-radius: 24px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid rgba(255, 255, 255, 0.08);
	  }}
	  code {{
		padding: 2px 6px;
		border-radius: 8px;
		background: rgba(255, 255, 255, 0.08);
	  }}
	</style>
  </head>
  <body>
	<main>
	  <h1>VinMec MedChat</h1>
	  <p>Giao diện React chưa được build.</p>
	  <p>Chạy <code>cd frontend && npm install && npm run dev</code> để phát triển hoặc <code>npm run build</code> rồi tải lại server này.</p>
	  <p>Kiểm tra trạng thái: <code>/api/health</code></p>
	</main>
  </body>
</html>"""


class ChatHandler(BaseHTTPRequestHandler):
	def log_message(self, format: str, *args) -> None:  # noqa: A003
		logger.info(format % args)

	def end_headers(self) -> None:
		self.send_header("Access-Control-Allow-Origin", "*")
		self.send_header("Access-Control-Allow-Headers", "Content-Type")
		self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
		super().end_headers()

	def do_OPTIONS(self) -> None:
		self.send_response(HTTPStatus.NO_CONTENT)
		self.end_headers()

	def do_GET(self) -> None:
		parsed_url = urlparse(self.path)
		request_path = parsed_url.path

		if request_path == "/api/health":
			json_response(
				self,
				HTTPStatus.OK,
				{
					"status": "ok",
					"model": OLLAMA_MODEL,
					"frontend": "đã build" if FRONTEND_DIST.exists() else "chế độ phát triển",
				},
			)
			return

		if FRONTEND_DIST.exists():
			relative_path = unquote(request_path.lstrip("/"))
			if not relative_path or request_path == "/":
				relative_path = "index.html"

			candidate = (FRONTEND_DIST / relative_path).resolve()
			try:
				candidate.relative_to(FRONTEND_DIST.resolve())
			except ValueError:
				self.send_error(HTTPStatus.FORBIDDEN)
				return

			if candidate.is_dir():
				candidate = candidate / "index.html"

			if candidate.exists():
				serve_static_file(self, candidate)
				return

			index_file = FRONTEND_DIST / "index.html"
			if index_file.exists():
				serve_static_file(self, index_file)
				return

			self.send_error(HTTPStatus.NOT_FOUND)
			return

		if request_path in {"/", "/index.html"}:
			html_response(self, HTTPStatus.OK, render_dev_fallback())
			return

		self.send_error(HTTPStatus.NOT_FOUND)

	def do_POST(self) -> None:
		parsed_url = urlparse(self.path)
		if parsed_url.path == "/api/evaluation":
			try:
				payload = read_json_body(self)
				model = str(payload.get("model") or OLLAMA_MODEL).strip()
				prompts = payload.get("prompts") or EVALUATION_PROMPTS
				if not isinstance(prompts, list) or not prompts:
					raise ValueError("'prompts' must be a non-empty list")

				rows = []
				llm_latencies = []
				agent_latencies = []

				for prompt in prompts:
					prompt_text = str(prompt).strip()
					if not prompt_text:
						continue

					llm_reply, llm_usage, llm_latency = run_llm_response(model, prompt_text)
					agent_reply, agent_usage, agent_latency = run_agent_response(model, prompt_text)
					llm_latencies.append(llm_latency)
					agent_latencies.append(agent_latency)

					tracker.track_request(
						provider="ollama",
						model=model,
						usage=llm_usage,
						latency_ms=llm_latency,
					)
					tracker.track_request(
						provider="ollama",
						model=model,
						usage=agent_usage,
						latency_ms=agent_latency,
					)

					rows.append(
						{
							"prompt": prompt_text,
							"llm": {
								"reply": llm_reply,
								"latency_ms": llm_latency,
								"usage": llm_usage,
							},
							"agent": {
								"reply": agent_reply,
								"latency_ms": agent_latency,
								"usage": agent_usage,
							},
						}
					)

				avg_llm_latency = int(sum(llm_latencies) / max(len(llm_latencies), 1))
				avg_agent_latency = int(sum(agent_latencies) / max(len(agent_latencies), 1))
				logger.log_event(
					"EVALUATION_RUN",
					{
						"model": model,
						"prompt_count": len(rows),
						"avg_llm_latency_ms": avg_llm_latency,
						"avg_agent_latency_ms": avg_agent_latency,
						"rows": rows,
					},
				)

				json_response(
					self,
					HTTPStatus.OK,
					{
						"model": model,
						"avg_llm_latency_ms": avg_llm_latency,
						"avg_agent_latency_ms": avg_agent_latency,
						"rows": rows,
					},
				)
			except ValueError as exc:
				json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
			except Exception as exc:  # noqa: BLE001
				logger.error(f"Evaluation request failed: {exc}")
				json_response(
					self,
					HTTPStatus.INTERNAL_SERVER_ERROR,
					{"error": "Không thể chạy đánh giá."},
				)
			return

		if parsed_url.path != "/api/chat":
			self.send_error(HTTPStatus.NOT_FOUND)
			return

		try:
			payload = read_json_body(self)
			messages = normalize_messages(payload.get("messages"))
			model = str(payload.get("model") or OLLAMA_MODEL).strip()
			use_agent = should_use_agent(payload)
			start_time = time.time()

			if use_agent:
				provider = OllamaProvider(model_name=model, client=OLLAMA_CLIENT)
				agent = ReActAgent(llm=provider, tools=TOOLS)
				user_input = messages[-1]["content"]
				content = agent.run(user_input)
				latency_ms = int((time.time() - start_time) * 1000)
				usage_payload = {
					"prompt_tokens": 0,
					"completion_tokens": 0,
					"total_tokens": 0,
				}
				source = "AGENT"
			else:
				response = OLLAMA_CLIENT.chat(
					model=model,
					messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
				)
				latency_ms = int((time.time() - start_time) * 1000)
				content = response["message"]["content"].strip()
				usage = response.get("usage", {})
				usage_payload = {
					"prompt_tokens": usage.get("prompt_tokens", 0),
					"completion_tokens": usage.get("completion_tokens", 0),
					"total_tokens": usage.get("total_tokens", 0),
				}
				source = "LLM"

			tracker.track_request(
				provider="ollama",
				model=model,
				usage=usage_payload,
				latency_ms=latency_ms,
			)
			logger.log_event(
				"CHAT_API_RESPONSE",
				{
					"model": model,
					"latency_ms": latency_ms,
					"message_count": len(messages),
					"source": source,
				},
			)

			json_response(
				self,
				HTTPStatus.OK,
				{
					"reply": content,
					"model": model,
					"latency_ms": latency_ms,
					"source": source,
					"usage": usage_payload,
				},
			)
		except ValueError as exc:
			json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
		except Exception as exc:  # noqa: BLE001
			logger.error(f"Chat request failed: {exc}")
			json_response(
				self,
				HTTPStatus.INTERNAL_SERVER_ERROR,
				{"error": "Không thể tạo phản hồi từ mô hình cục bộ."},
			)


def main() -> None:
	port = int(os.getenv("PORT", "8000"))
	server = ThreadingHTTPServer(("0.0.0.0", port), ChatHandler)
	print(f"Serving VinMec MedChat on http://127.0.0.1:{port}")
	server.serve_forever()


if __name__ == "__main__":
	main()
