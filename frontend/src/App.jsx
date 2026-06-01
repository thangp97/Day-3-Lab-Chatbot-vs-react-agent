import { useEffect, useRef, useState } from 'react';

const starterPrompts = [
  'Tôi cần làm gì trước khi phẫu thuật?',
  'Ngày đầu sau mổ tôi có thể ăn gì?',
  'Khi nào vết mổ sưng đỏ thì cần lo ngại?',
  'Sau phẫu thuật bao lâu thì được tắm?',
];

const initialMessages = [
  {
    id: 'welcome',
    role: 'assistant',
    content:
      'Xin chào, tôi là MedChat. Bạn có thể hỏi tôi về chuẩn bị trước mổ, hồi phục sau mổ, chăm sóc vết mổ hoặc lịch tái khám. Tôi đang chạy trên mô hình Qwen cục bộ qua Ollama.',
  },
];

function createMessage(role, content, extra = {}) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    ...extra,
  };
}

function formatLatency(latencyMs) {
  if (!latencyMs) {
    return 'local';
  }
  if (latencyMs < 1000) {
    return `${latencyMs} ms`;
  }
  return `${(latencyMs / 1000).toFixed(1)} s`;
}

function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState('llm');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [serverInfo, setServerInfo] = useState({ model: 'Qwen cục bộ', status: 'Đang kiểm tra...' });
  const [evaluation, setEvaluation] = useState(null);
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [evaluationError, setEvaluationError] = useState('');
  const messagesRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    const container = messagesRef.current;
    if (!container) {
      return;
    }
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    fetch('/api/health')
      .then((response) => response.json())
      .then((data) => {
        setServerInfo({
          model: data.model || 'Qwen cục bộ',
          status: data.status || 'Sẵn sàng',
        });
      })
      .catch(() => {
        setServerInfo({ model: 'Qwen cục bộ', status: 'Ngoại tuyến' });
      });
  }, []);

  const resizeTextarea = () => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  };

  const sendMessage = async (text) => {
    const content = text.trim();
    if (!content || loading) {
      return;
    }

    setError('');
    const nextMessages = [...messages, createMessage('user', content)];
    setMessages(nextMessages);
    setDraft('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content: messageContent }) => ({
            role,
            content: messageContent,
          })),
          mode,
        }),
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || 'Yêu cầu chat thất bại');
      }

      const data = await response.json();
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage('assistant', data.reply || 'Không nhận được phản hồi.', {
          model: data.model,
          latencyMs: data.latency_ms,
          source: data.source,
        }),
      ]);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'Lỗi không xác định';
      setError(message);
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage('assistant', 'Xin lỗi, mô hình cục bộ hiện chưa thể trả lời yêu cầu này.'),
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    await sendMessage(draft);
    resizeTextarea();
  };

  const handlePromptClick = async (prompt) => {
    await sendMessage(prompt);
  };

  const runEvaluation = async () => {
    setEvaluationError('');
    setEvaluationLoading(true);

    try {
      const response = await fetch('/api/evaluation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || 'Không thể chạy đánh giá');
      }

      const data = await response.json();
      setEvaluation(data);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'Lỗi không xác định';
      setEvaluationError(message);
    } finally {
      setEvaluationLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <div className="background-glow glow-a" />
      <div className="background-glow glow-b" />

      <aside className="sidebar">
        <div className="brand-card">
          <div className="brand-mark">M</div>
          <div>
            <p className="eyebrow">Trò chuyện AI cục bộ</p>
            <h1>VinMec MedChat</h1>
          </div>
        </div>

        <section className="panel">
          <div className="panel-label">Mô hình</div>
          <div className="status-row">
            <span className="status-dot" />
            <div>
              <div className="status-title">{serverInfo.model}</div>
              <div className="status-subtitle">{serverInfo.status}</div>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-label">Gợi ý nhanh</div>
          <div className="prompt-list">
            {starterPrompts.map((prompt) => (
              <button key={prompt} type="button" className="prompt-chip" onClick={() => handlePromptClick(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="panel soft">
          <div className="panel-label">Luồng xử lý</div>
          <p className="panel-copy">
            Giao diện chat gửi toàn bộ lịch sử tin nhắn đến <span>/api/chat</span>, rồi backend Python chuyển tiếp tới mô hình Ollama cục bộ.
          </p>
          <div className="mini-stat-grid">
            <div>
              <span>Truyền dữ liệu</span>
              <strong>HTTP JSON</strong>
            </div>
            <div>
              <span>Backend</span>
              <strong>Python</strong>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-label">Evaluation 7đ</div>
          <button type="button" className="eval-button" onClick={runEvaluation} disabled={evaluationLoading}>
            {evaluationLoading ? 'Đang chạy đánh giá...' : 'Chạy bảng so sánh'}
          </button>
          {evaluationError ? <p className="panel-error">{evaluationError}</p> : null}
        </section>
      </aside>

      <main className="chat-card">
        <header className="chat-topbar">
          <div>
            <p className="eyebrow">Cuộc trò chuyện</p>
            <h2>Hỏi mô hình cục bộ như một ứng dụng chat thật sự</h2>
          </div>
          <div className="badge-row">
            <span className="badge">Ollama</span>
            <span className="badge badge-accent">Qwen</span>
          </div>
        </header>

        {evaluation ? (
          <section className="evaluation-card">
            <div className="evaluation-header">
              <div>
                <p className="eyebrow">Evaluation 7đ</p>
                <h3>Bảng so sánh Chatbot vs Agent</h3>
              </div>
              <div className="evaluation-stats">
                <span>LLM TB: {formatLatency(evaluation.avg_llm_latency_ms)}</span>
                <span>Agent TB: {formatLatency(evaluation.avg_agent_latency_ms)}</span>
              </div>
            </div>
            <div className="evaluation-table">
              <div className="evaluation-row evaluation-head">
                <span>Prompt</span>
                <span>LLM</span>
                <span>Agent</span>
              </div>
              {evaluation.rows?.map((row, index) => (
                <div key={`${row.prompt}-${index}`} className="evaluation-row">
                  <div className="evaluation-cell">
                    <strong>{row.prompt}</strong>
                  </div>
                  <div className="evaluation-cell">
                    <p>{row.llm.reply}</p>
                    <span className="evaluation-meta">{formatLatency(row.llm.latency_ms)}</span>
                  </div>
                  <div className="evaluation-cell">
                    <p>{row.agent.reply}</p>
                    <span className="evaluation-meta">{formatLatency(row.agent.latency_ms)}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="message-stream" ref={messagesRef}>
          {messages.map((message) => (
            <article key={message.id} className={`message-row ${message.role}`}>
              <div className="avatar">{message.role === 'assistant' ? 'AI' : 'Bạn'}</div>
              <div className="message-bubble">
                <div className="message-content">{message.content}</div>
                {message.role === 'assistant' && (message.model || message.latencyMs || message.source) ? (
                  <div className="message-meta">
                    {message.source ? <span className="badge-source">{message.source}</span> : null}
                    {message.model ? <span>{message.model}</span> : null}
                    {message.latencyMs ? <span>{formatLatency(message.latencyMs)}</span> : null}
                  </div>
                ) : null}
              </div>
            </article>
          ))}

          {loading ? (
            <article className="message-row assistant">
              <div className="avatar">AI</div>
              <div className="message-bubble typing">
                <div className="typing-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </article>
          ) : null}
        </section>

        <div className="composer-shell">
          {error ? <div className="error-banner">{error}</div> : null}

          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              ref={textareaRef}
              className="composer-input"
              value={draft}
              placeholder="Nhập câu hỏi y khoa của bạn ở đây..."
              rows={1}
              onChange={(event) => {
                setDraft(event.target.value);
                resizeTextarea();
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit(event);
                }
              }}
            />
            <div className="mode-toggle" role="group" aria-label="Chọn chế độ">
              <button
                type="button"
                className={`mode-button ${mode === 'llm' ? 'active' : ''}`}
                onClick={() => setMode('llm')}
                disabled={loading}
              >
                LLM
              </button>
              <button
                type="button"
                className={`mode-button ${mode === 'agent' ? 'active' : ''}`}
                onClick={() => setMode('agent')}
                disabled={loading}
              >
                Agent
              </button>
            </div>
            <button type="submit" className="send-button" disabled={loading || !draft.trim()}>
              {loading ? 'Đang suy nghĩ...' : 'Gửi'}
            </button>
          </form>

          <p className="composer-hint">Nhấn Enter để gửi, Shift + Enter để xuống dòng.</p>
        </div>
      </main>
    </div>
  );
}

export default App;
