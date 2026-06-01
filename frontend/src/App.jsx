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

const MODES = [
  { value: 'llm',      label: 'LLM' },
  { value: 'agent_v1', label: 'Agent v1' },
  { value: 'agent_v2', label: 'Agent v2' },
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
  if (!latencyMs) return '—';
  if (latencyMs < 1000) return `${latencyMs} ms`;
  return `${(latencyMs / 1000).toFixed(1)} s`;
}

function formatTokens(usage) {
  if (!usage) return '—';
  const t = usage.total_tokens || 0;
  if (!t) return '—';
  return `${t} tok`;
}

function EvalTable({ evalData, colA, colB }) {
  if (!evalData) return null;
  return (
    <section className="evaluation-card">
      <div className="evaluation-header">
        <div>
          <p className="eyebrow">Evaluation</p>
          <h3>
            Bảng so sánh {colA} vs {colB}
          </h3>
        </div>
        <div className="evaluation-stats">
          <span>
            {colA} TB: {formatLatency(evalData[`avg_${colA.toLowerCase().replace(' ', '_')}_latency_ms`]
              || evalData.avg_llm_latency_ms || evalData.avg_v1_latency_ms)}
          </span>
          <span>
            {colB} TB: {formatLatency(evalData[`avg_${colB.toLowerCase().replace(' ', '_')}_latency_ms`]
              || evalData.avg_agent_latency_ms || evalData.avg_v2_latency_ms)}
          </span>
        </div>
      </div>
      <div className="evaluation-table">
        <div className="evaluation-row evaluation-head">
          <span>Prompt</span>
          <span>{colA}</span>
          <span>{colB}</span>
        </div>
        {evalData.rows?.map((row, index) => {
          const dataA = row.llm || row.v1;
          const dataB = row.agent || row.v2;
          return (
            <div key={`${row.prompt}-${index}`} className="evaluation-row">
              <div className="evaluation-cell">
                <strong>{row.prompt}</strong>
              </div>
              <div className="evaluation-cell">
                <p>{dataA?.reply}</p>
                <div className="evaluation-meta-row">
                  <span className="evaluation-meta">{formatLatency(dataA?.latency_ms)}</span>
                  {dataA?.usage?.total_tokens ? (
                    <span className="evaluation-meta evaluation-tokens">
                      {dataA.usage.prompt_tokens}p + {dataA.usage.completion_tokens}c ={' '}
                      {dataA.usage.total_tokens} tok
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="evaluation-cell">
                <p>{dataB?.reply}</p>
                <div className="evaluation-meta-row">
                  <span className="evaluation-meta">{formatLatency(dataB?.latency_ms)}</span>
                  {dataB?.usage?.total_tokens ? (
                    <span className="evaluation-meta evaluation-tokens">
                      {dataB.usage.prompt_tokens}p + {dataB.usage.completion_tokens}c ={' '}
                      {dataB.usage.total_tokens} tok
                    </span>
                  ) : null}
                  {dataB?.steps ? (
                    <span className="evaluation-meta evaluation-steps">{dataB.steps} steps</span>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState('');
  const [mode, setMode] = useState('llm');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [serverInfo, setServerInfo] = useState({ model: 'Qwen cục bộ', status: 'Đang kiểm tra...' });

  // Evaluation: LLM vs Agent v2
  const [evaluation, setEvaluation] = useState(null);
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [evaluationError, setEvaluationError] = useState('');

  // Evaluation: Agent v1 vs v2
  const [agentCompare, setAgentCompare] = useState(null);
  const [agentCompareLoading, setAgentCompareLoading] = useState(false);
  const [agentCompareError, setAgentCompareError] = useState('');

  const messagesRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((data) => setServerInfo({ model: data.model || 'Qwen cục bộ', status: data.status || 'Sẵn sàng' }))
      .catch(() => setServerInfo({ model: 'Qwen cục bộ', status: 'Ngoại tuyến' }));
  }, []);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  const sendMessage = async (text) => {
    const content = text.trim();
    if (!content || loading) return;

    setError('');
    const nextMessages = [...messages, createMessage('user', content)];
    setMessages(nextMessages);
    setDraft('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content: c }) => ({ role, content: c })),
          mode,
        }),
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || 'Yêu cầu chat thất bại');
      }

      const data = await response.json();
      setMessages((cur) => [
        ...cur,
        createMessage('assistant', data.reply || 'Không nhận được phản hồi.', {
          model: data.model,
          latencyMs: data.latency_ms,
          source: data.source,
          tokens: data.usage?.total_tokens,
        }),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi không xác định');
      setMessages((cur) => [...cur, createMessage('assistant', 'Xin lỗi, mô hình cục bộ hiện chưa thể trả lời yêu cầu này.')]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await sendMessage(draft);
    resizeTextarea();
  };

  const runEvaluation = async () => {
    setEvaluationError('');
    setEvaluationLoading(true);
    try {
      const r = await fetch('/api/evaluation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error((await r.text()) || 'Không thể chạy đánh giá');
      setEvaluation(await r.json());
    } catch (err) {
      setEvaluationError(err instanceof Error ? err.message : 'Lỗi không xác định');
    } finally {
      setEvaluationLoading(false);
    }
  };

  const runAgentCompare = async () => {
    setAgentCompareError('');
    setAgentCompareLoading(true);
    try {
      const r = await fetch('/api/evaluation/agent-compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error((await r.text()) || 'Không thể so sánh agent');
      setAgentCompare(await r.json());
    } catch (err) {
      setAgentCompareError(err instanceof Error ? err.message : 'Lỗi không xác định');
    } finally {
      setAgentCompareLoading(false);
    }
  };

  const modeLabel = MODES.find((m) => m.value === mode)?.label ?? mode;

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
              <button key={prompt} type="button" className="prompt-chip" onClick={() => sendMessage(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="panel soft">
          <div className="panel-label">Chế độ hiện tại</div>
          <p className="panel-copy">
            Đang dùng: <span>{modeLabel}</span>. Dùng nút bên dưới ô nhập để chuyển giữa{' '}
            <span>LLM</span>, <span>Agent v1</span> (không có bảo mật / few-shot) và{' '}
            <span>Agent v2</span> (đầy đủ cải tiến).
          </p>
          <div className="mini-stat-grid">
            <div>
              <span>Backend</span>
              <strong>Python</strong>
            </div>
            <div>
              <span>LLM</span>
              <strong>Ollama</strong>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-label">Evaluation LLM vs Agent v2</div>
          <button
            type="button"
            className="eval-button"
            onClick={runEvaluation}
            disabled={evaluationLoading || agentCompareLoading}
          >
            {evaluationLoading ? 'Đang chạy...' : 'Chạy bảng so sánh (7đ)'}
          </button>
          {evaluationError ? <p className="panel-error">{evaluationError}</p> : null}
        </section>

        <section className="panel">
          <div className="panel-label">Evaluation Agent v1 vs v2</div>
          <button
            type="button"
            className="eval-button eval-button-secondary"
            onClick={runAgentCompare}
            disabled={agentCompareLoading || evaluationLoading}
          >
            {agentCompareLoading ? 'Đang so sánh...' : 'So sánh Agent v1 vs v2'}
          </button>
          {agentCompareError ? <p className="panel-error">{agentCompareError}</p> : null}
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
            <span className="badge badge-accent">{modeLabel}</span>
          </div>
        </header>

        {evaluation ? <EvalTable evalData={evaluation} colA="LLM" colB="Agent v2" /> : null}
        {agentCompare ? <EvalTable evalData={agentCompare} colA="Agent v1" colB="Agent v2" /> : null}

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
                    {message.tokens ? <span>{message.tokens} tok</span> : null}
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
              onChange={(e) => {
                setDraft(e.target.value);
                resizeTextarea();
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <div className="mode-toggle" role="group" aria-label="Chọn chế độ">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  className={`mode-button ${mode === m.value ? 'active' : ''}`}
                  onClick={() => setMode(m.value)}
                  disabled={loading}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button type="submit" className="send-button" disabled={loading || !draft.trim()}>
              {loading ? 'Đang suy nghĩ...' : 'Gửi'}
            </button>
          </form>

          <p className="composer-hint">Nhấn Enter để gửi · Shift+Enter xuống dòng · Chế độ: {modeLabel}</p>
        </div>
      </main>
    </div>
  );
}

export default App;
