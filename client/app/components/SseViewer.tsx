"use client"; // Marks this file as a Client Component

import { useEffect, useState } from "react";

interface SSEData {
  message: string;
  count: number;
}

export default function SseViewer() {
  const [messages, setMessages] = useState<string[]>([]);
  const [status, setStatus] = useState<"Connecting" | "Connected" | "Disconnected">("Disconnected");

  useEffect(() => {
    setStatus("Connecting");
    
    // 1. Establish connection to the FastAPI endpoint
    const eventSource = new EventSource("http://localhost:8000/api/sse");

    // 2. Event triggered when the connection successfully opens
    eventSource.onopen = () => {
      setStatus("Connected");
    };

    // 3. Main event listener for processing incoming stream data
    eventSource.onmessage = (event) => {
      try {
        // Parse incoming text into JavaScript objects
        // (Note: Replace single quotes with double quotes if backend yields malformed JSON)
        const validJsonString = event.data.replace(/'/g, '"');
        const parsedData: SSEData = JSON.parse(validJsonString);
        
        setMessages((prev) => [...prev, `${parsedData.message} (#${parsedData.count})`]);
      } catch (err) {
        console.error("Error parsing stream event:", err);
      }
    };

    // 4. Fallback handling for network Drops or Backend crash
    eventSource.onerror = (error) => {
      console.error("EventSource encountered an error:", error);
      setStatus("Disconnected");
      eventSource.close(); // Stop browser from infinitely looping retries if server goes down
    };

    // 5. Critical: Close the connection instantly when the user navigates away
    return () => {
      eventSource.close();
      setStatus("Disconnected");
    };
  }, []);

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
        {messages.length === 0 ? (
          <p className="text-gray-400 italic">Waiting for events...</p>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className="text-gray-700 font-mono">⏱️ {msg}</div>
          ))
        )}
      </div>
    </div>
  );
}
