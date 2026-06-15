"use client"; // Marks this file as a Client Component

import { useRef, useEffect, useState } from "react";

interface SSEData {
  delta?: string;
  done?: boolean;
}

export default function SseViewer() {
  const [streaming, setStreaming] = useState<string>("");
  const [prompt, setPrompt] = useState("")
  const [status, setStatus] = useState<"Connecting" | "Connected" | "Disconnected">("Disconnected");
  const esRef = useRef<EventSource | null>(null)

  const onSubmit = () => {
    setStreaming("")
    esRef.current?.close()
    setStatus("Connecting");
    
    // 1. Establish connection to the FastAPI endpoint
    const es = new EventSource(`http://localhost:8000/api/chat?message=${encodeURIComponent(prompt)}`);
    esRef.current = es

    // 2. Event triggered when the connection successfully opens
    es.onopen = () => {
      setStatus("Connected");
    };

    // 3. Main event listener for processing incoming stream data
    es.onmessage = (event) => {
      try {
        // parse incoming JSON
        const parsedData: SSEData = JSON.parse(event.data);
        // to avoid the trap of having an infinite loop (since
        // event source reopens if not close, which causes this prompt to be sent again)
        // after hitting the sentinel value "done", close the event source
        if (parsedData.done){
          es.close()
          setStatus("Disconnected")
          return
        }
        
        // as the stream comes in, append to an existing string,
        // this should create that "typewriter" effect as 
        // the deltas from the LLM are returned
        setStreaming((prev) => prev + parsedData.delta);
      } catch (err) {
        console.error("Error parsing stream event:", err);
      }
    };

    // 4. Fallback handling for network Drops or Backend crash
    es.onerror = (error) => {
      console.error("EventSource encountered an error:", error);
      setStatus("Disconnected");
      es.close(); // Stop browser from infinitely looping retries if server goes down
    };

  }

  useEffect(() => {
    return () => esRef.current?.close()
  }, [])

  return (
    <div className="p-6 max-w-md mx-auto border rounded-xl shadow-md space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">FastAPI Real-time Stream</h2>
        <span className={`px-2 py-1 text-xs font-semibold rounded ${
          status === "Connected" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
        }`}>
          {status}
        </span>
      </div>
      <div className="h-48 overflow-y-auto bg-gray-50 p-3 rounded border text-sm space-y-1">
        <div className="text-gray-700 font-mono">{streaming}</div>
      </div>
      <form onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }} className = "flex flex-row gap-x-2">
        <input onChange={(e) => {
          setPrompt(e.target.value)
        }} type="text" className = "p-1 w-full rounded border" placeholder="Type in the chat here..."/>
        <button type="submit" className = "border rounded p-1">Submit</button>
      </form>
    </div>
  );
}
