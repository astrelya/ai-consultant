import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { ChatMessage } from "../types";

export default function Chat() {
  const { id: projectId = "", sessionId: paramSessionId } = useParams();
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | null>(paramSessionId ?? null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState("");
  const [connected, setConnected] = useState(false);
  const [genRun, setGenRun] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sessionId && projectId) {
      api.createChatSession(projectId).then((s) => {
        setSessionId(s.id);
        navigate(`/projects/${projectId}/chat/${s.id}`, { replace: true });
      });
    }
  }, [projectId, sessionId, navigate]);

  useEffect(() => {
    if (!sessionId) return;
    api.getChatSession(sessionId).then((r) => setMessages(r.messages));
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/ws/chat-sessions/${sessionId}`);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === "user_message") {
        setMessages((m) => [...m, {
          id: data.id, session_id: sessionId, role: "user", content: data.content, created_at: new Date().toISOString(),
        }]);
      } else if (data.type === "assistant_start") {
        setStreaming("");
      } else if (data.type === "assistant_delta") {
        setStreaming((s) => s + data.delta);
      } else if (data.type === "assistant_end") {
        setStreaming("");
        setMessages((m) => [...m, {
          id: data.id, session_id: sessionId, role: "assistant", content: data.content, created_at: new Date().toISOString(),
        }]);
      } else if (data.type === "error") {
        setStreaming("");
        alert(`Chat error: ${data.message}`);
      }
    };
    return () => ws.close();
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  function send() {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content: input.trim() }));
    setInput("");
  }

  async function generate() {
    if (!sessionId) return;
    const run = await api.generateTickets(sessionId);
    setGenRun(run.id);
    setTimeout(() => navigate("/tickets"), 1500);
  }

  return (
    <div>
      <div className="row spread">
        <h2>Brainstorm</h2>
        <div className="row">
          <Link to={`/projects/${projectId}`}><button className="ghost">← Project</button></Link>
          <button onClick={generate} disabled={messages.length === 0}>Generate tickets</button>
        </div>
      </div>
      <div className="muted">
        WS: {connected ? "connected" : "connecting…"} {genRun && `· drafting run ${genRun.slice(0, 8)}…`}
      </div>

      <div className="chat-container" style={{ marginTop: 16 }}>
        <div className="chat-messages">
          {messages.map((m) => (
            <div key={m.id} className={`chat-msg ${m.role}`}>{m.content}</div>
          ))}
          {streaming && <div className="chat-msg assistant">{streaming}</div>}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            placeholder="Describe your feature idea…"
          />
          <button onClick={send} disabled={!connected}>Send</button>
        </div>
      </div>
    </div>
  );
}
