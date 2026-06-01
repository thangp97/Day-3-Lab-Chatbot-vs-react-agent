# chatbot.py — Baseline KHÔNG có tools để so sánh với Agent
import os
import time
from dotenv import load_dotenv
import ollama
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker

load_dotenv()

SYSTEM_PROMPT = (
    "Bạn là trợ lý bệnh viện. Trả lời câu hỏi của bệnh nhân về phẫu thuật. "
    "Không có khả năng tra cứu tài liệu — trả lời từ kiến thức chung."
)

def _resolve_ollama_model() -> str:
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()
    if model_name == "qwen2.5":
        return "qwen2.5:7b"
    return model_name


OLLAMA_MODEL = _resolve_ollama_model()
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

TEST_CASES = [
    "Trước khi mổ ruột thừa cần nhịn ăn bao lâu?",
    "Sau mổ tôi được ăn gì vào ngày đầu tiên?",
    "Vết mổ bị đỏ và sưng, tôi có cần đến viện không?",
    "Khi nào tôi được tắm sau phẫu thuật?",
    "Tái khám sau mổ ruột thừa vào ngày nào?",
]

def run():
    print("=" * 60)
    print(f"CHATBOT BASELINE LOCAL QWEN ({OLLAMA_MODEL})")
    print("=" * 60)

    client = ollama.Client(host=OLLAMA_HOST) if OLLAMA_HOST else ollama.Client()

    for query in TEST_CASES:
        print(f"\nUser   : {query}")
        start_time = time.time()
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        latency_ms = int((time.time() - start_time) * 1000)

        content = response["message"]["content"].strip()
        usage = response.get("usage", {})
        result = {
            "content": content,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "latency_ms": latency_ms,
            "provider": "ollama",
        }

        tracker.track_request(
            provider=result["provider"],
            model=OLLAMA_MODEL,
            usage=result["usage"],
            latency_ms=result["latency_ms"],
        )
        logger.log_event("CHATBOT_RESPONSE", {
            "input": query,
            "output": content,
            "model": OLLAMA_MODEL,
            "latency_ms": result["latency_ms"],
        })
        print(f"Chatbot: {content[:200]}...")   # in 200 ký tự đầu
        print("-" * 60)

if __name__ == "__main__":
    run()