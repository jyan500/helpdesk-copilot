"use client";

import { useEffect, useRef, useState } from "react";

// Phase 3 — the Knowledge (RAG) agent. This is a near-twin of AccountChat: it
// consumes the SAME event contract (server/agent/loop.py stream_knowledge_agent),
//   {type:"tool",  name, args}  -> a tool is running (here it's search_docs)
//   {type:"delta", text}        -> a chunk of the answer (typewriter)
//   {type:"done"}               -> stream finished
// so the only real differences are the endpoint it hits and the copy. (Phase 4's
// orchestrator is where a single box decides account-vs-knowledge for you.)
interface AgentEvent {
  type: "tool" | "delta" | "done";
  name?: string;
  args?: Record<string, unknown>;
  text?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

type Status = "idle" | "thinking" | "streaming";

export default function KnowledgeChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, toolActivity]);

  const onSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || status !== "idle") return;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: trimmed },
      { role: "assistant", content: "" },
    ]);
    setInput("");
    setStatus("thinking");
    setToolActivity(null);

    esRef.current?.close();
    // The only backend difference vs AccountChat: the knowledge endpoint.
    const es = new EventSource(
      `http://localhost:8000/api/knowledge/chat?message=${encodeURIComponent(trimmed)}`
    );
    esRef.current = es;

    es.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);

      if (event.type === "tool") {
        setStatus("thinking");
        // e.g. "Searching the help center…" — the knowledge agent's one tool.
        setToolActivity(`Running ${event.name}…`);
      }

      if (event.type === "delta") {
        setStatus("streaming");
        setToolActivity(null);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + (event.text ?? "") };
          return next;
        });
      }

      if (event.type === "done") {
        es.close();
        setStatus("idle");
        setToolActivity(null);
      }
    };

    es.onerror = () => {
      es.close();
      setStatus("idle");
      setToolActivity(null);
    };
  };

  useEffect(() => () => esRef.current?.close(), []);

  return (
    <div className="p-6 w-full max-w-xl mx-auto border rounded-xl shadow-md flex flex-col gap-y-4 bg-white">
      <h2 className="text-xl font-bold">Helpdesk Copilot — Knowledge agent</h2>

      <div
        ref={scrollRef}
        className="h-96 overflow-y-auto bg-gray-50 p-3 rounded border flex flex-col gap-y-3 text-sm"
      >
        {messages.length === 0 && (
          <p className="text-gray-400">
            Try: “How long do refunds take?” or “What are your support hours?”
          </p>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "self-end max-w-[85%]" : "self-start max-w-[85%]"}
          >
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-0.5">
              {m.role}
            </div>
            <div
              className={`rounded-lg px-3 py-2 whitespace-pre-wrap ${
                m.role === "user" ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-900"
              }`}
            >
              {m.content || (status !== "idle" ? "…" : "")}
            </div>
          </div>
        ))}

        {toolActivity && (
          <div className="self-start text-xs text-amber-700 italic">{toolActivity}</div>
        )}
        {status === "thinking" && !toolActivity && (
          <div className="self-start text-xs text-gray-500 italic">Thinking…</div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="flex flex-row gap-x-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={status !== "idle"}
          type="text"
          className="p-2 w-full rounded border disabled:bg-gray-100"
          placeholder="Ask a how-do-I or policy question…"
        />
        <button
          type="submit"
          disabled={status !== "idle" || !input.trim()}
          className="border rounded px-4 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
