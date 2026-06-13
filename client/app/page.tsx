"use client"
import Image from "next/image";
import SseViewer from "@/app/components/SseViewer"

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <SseViewer/>   
    </div>
  );
}
