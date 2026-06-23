"use client"
import AccountChat from "@/app/components/AccountChat"
import KnowledgeChat from "@/app/components/KnowledgeChat"

export default function Home() {
  return (
    <div className="text-slate-600 flex flex-col flex-1 items-center justify-center gap-y-8 bg-zinc-50 font-sans dark:bg-black p-6">
      <AccountChat/>
      <KnowledgeChat/>
    </div>
  );
}
