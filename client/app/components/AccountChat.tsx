"use client";

import { useEffect, useRef, useState } from "react";

// Mirror of the backend event contract (server/agent/loop.py stream_account_agent):
//   {type:"tool",  name, args}  -> a tool is running (show as loading/progress)
//   {type:"delta", text}        -> a chunk of the answer (append to typewriter)
//   {type:"done"}               -> stream finished
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

export default function AccountChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep the transcript scrolled to the newest content as it streams in.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, toolActivity]);

  const onSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || status !== "idle") return;

    // Push the user's message AND an empty assistant message we'll fill in as
    // deltas stream back. (So index messages.length-1 is "the answer so far".)
    setMessages((prev) => [
      ...prev,
      { role: "user", content: trimmed },
      { role: "assistant", content: "" },
    ]);
    setInput("");
    setStatus("thinking");
    setToolActivity(null);

    esRef.current?.close();
    const es = new EventSource(
      `http://localhost:8000/api/agent/chat?message=${encodeURIComponent(trimmed)}`
    );
    esRef.current = es;

    es.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);

      // TODO: handle each event type. Pointers:
      //
      //   if event.type === "tool":
      //       setStatus("thinking");
      //       setToolActivity(`Running ${event.name}…`);   // e.g. "Running get_customer…"
      //
      //   if event.type === "delta":
      //       setStatus("streaming");
      //       setToolActivity(null);
      //       // Append event.text to the LAST (assistant) message IMMUTABLY —
      //       // never mutate prev in place, or React won't re-render:
      //       setMessages((prev) => {
      //         const next = [...prev];
      //         const last = next[next.length - 1];
      //         next[next.length - 1] = { ...last, content: last.content + (event.text ?? "") };
      //         return next;
      //       });
      //
      //   if event.type === "done":
      //       es.close();
      //       setStatus("idle");
      //       setToolActivity(null);

      if (event.type === "tool"){
        setStatus("thinking") 
        setToolActivity(`Running ${event.name}...`)
      }

      if (event.type === "delta"){
        setStatus("streaming")
        setToolActivity(null)
        // originally, for each chat interaction,
        // we append one set of placeholder messages for the <user> and the <assistant>,
        // then as we receive "delta" content from the backend, we replace
        // that placeholder text
        // Append event.text to the LAST (assistant) message IMMUTABLY
        // never mutate prev in place, or React won't re-render
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length-1]
          next[next.length-1] = { ...last, content: last.content + (event.text ?? "")}
          return next
        })
      }

      if (event.type === "done"){
        es.close()
        setStatus("idle")
        setToolActivity(null)
      }

    };

    // Network drop / backend crash: stop the browser's auto-retry loop.
    es.onerror = () => {
      es.close();
      setStatus("idle");
      setToolActivity(null);
    };
  };

  // Close any open stream when the component unmounts.
  useEffect(() => () => esRef.current?.close(), []);

  return (
    <div className="p-6 w-full max-w-xl mx-auto border rounded-xl shadow-md flex flex-col gap-y-4 bg-white">
      <h2 className="text-xl font-bold">Helpdesk Copilot — Account agent</h2>

      <div
        ref={scrollRef}
        className="h-96 overflow-y-auto bg-gray-50 p-3 rounded border flex flex-col gap-y-3 text-sm"
      >
        {messages.length === 0 && (
          <p className="text-gray-400">
            Try: “What’s the status of the latest order for alice@example.com?”
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

        {/* Loading / tool-progress indicator */}
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
          placeholder="Ask about a customer, order, or subscription…"
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
