"use client";

import { useEffect, useRef, useState } from "react";

// Phase 4 — the ORCHESTRATOR chat. One box for everything: it hits the
// /api/orchestrator/chat endpoint, which classifies the message and routes it to
// the account or knowledge specialist internally. It consumes the SAME event
// contract as AccountChat/KnowledgeChat, PLUS one new event:
//   {type:"route", intent}      -> which specialist the orchestrator picked (NEW)
//   {type:"tool",  name, args}  -> a tool is running
//   {type:"delta", text}        -> a chunk of the answer (typewriter)
//   {type:"done"}               -> stream finished
interface AgentEvent {
  type: "route" | "tool" | "delta" | "done";
  intent?: string;
  name?: string;
  args?: Record<string, unknown>;
  text?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

type Status = "idle" | "thinking" | "streaming";

export default function OrchestratorChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  // The orchestrator's routing decision, shown so you can SEE the triage step.
  const [route, setRoute] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, toolActivity, route]);

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
    setRoute(null);

    esRef.current?.close();
    const es = new EventSource(
      `http://localhost:8000/api/orchestrator/chat?message=${encodeURIComponent(trimmed)}`
    );
    esRef.current = es;

    es.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);

      // NEW: the triage decision arrives first — surface it to the user.
      if (event.type === "route") {
        setRoute(event.intent ?? null);
      }

      if (event.type === "tool") {
        setStatus("thinking");
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
      <h2 className="text-xl font-bold">Helpdesk Copilot</h2>
      <p className="text-xs text-gray-400 -mt-2">
        One box — it figures out whether you&apos;re asking about an account or the help center.
      </p>

      <div
        ref={scrollRef}
        className="h-96 overflow-y-auto bg-gray-50 p-3 rounded border flex flex-col gap-y-3 text-sm"
      >
        {messages.length === 0 && (
          <p className="text-gray-400">
            Try: “What&apos;s alice@example.com&apos;s latest order?” or “How long do refunds take?”
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

        {route && (
          <div className="self-start text-xs text-indigo-700 italic">
            Routed to the {route} agent
          </div>
        )}
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
          placeholder="Ask anything — account or help-center…"
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
