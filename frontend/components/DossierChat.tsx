"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, MessageSquare } from "lucide-react";
import { useProfile } from "@/app/dashboard/ProfileContext";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface DossierChatProps {
  texteUid: string;
  texteTitle?: string;
}

export default function DossierChat({ texteUid, texteTitle }: DossierChatProps) {
  const { activeProfile } = useProfile();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const suggestions = [
    "Explique ce dossier simplement",
    "Propose des actions prioritaires",
    "Qui sont les acteurs cles a contacter ?",
  ];

  const handleSubmit = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = {
      id: String(Date.now()),
      role: "user",
      content: text.trim(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (typeof window !== "undefined") {
        const token = localStorage.getItem("legix_token");
        if (token) headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch("/api/chat", {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: text.trim(),
          agent: "analyste",
          texte_uid: texteUid,
        }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          role: "assistant",
          content: data.response || "Erreur de reponse.",
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          role: "assistant",
          content: "Erreur de connexion au serveur.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 flex items-center gap-2 rounded-full bg-dark px-5 py-3 text-sm font-medium text-white shadow-lg transition-transform hover:scale-105"
      >
        <MessageSquare className="h-4 w-4" />
        Chat dossier
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[500px] w-96 flex-col rounded-xl border border-border bg-white shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-xl border-b border-border bg-cream px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-warm" />
          <span className="text-sm font-semibold text-dark">
            Chat — {texteTitle ? texteTitle.slice(0, 30) + "..." : texteUid}
          </span>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="text-xs text-muted hover:text-dark"
        >
          Fermer
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3">
        {messages.length === 0 && (
          <div className="mt-4 text-center">
            <Bot className="mx-auto h-8 w-8 text-warm/30" />
            <p className="mt-2 text-xs text-muted">
              Posez vos questions sur ce dossier
            </p>
            <div className="mt-3 space-y-1.5">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSubmit(s)}
                  className="block w-full rounded-lg bg-cream px-3 py-1.5 text-left text-xs text-warm transition-colors hover:bg-cream-dark"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`mb-2 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed ${
                msg.role === "user"
                  ? "bg-dark text-white"
                  : "bg-cream text-dark"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-cream px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-warm" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); handleSubmit(input); }}
        className="border-t border-border p-2"
      >
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Question sur ce dossier..."
            className="flex-1 bg-transparent px-2 text-xs text-dark placeholder:text-muted/50 focus:outline-none"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-dark text-white disabled:opacity-50"
          >
            <Send className="h-3 w-3" />
          </button>
        </div>
      </form>
    </div>
  );
}
