"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Send, Bot, User, Loader2, Building2, FileText } from "lucide-react";
import { useProfile } from "../ProfileContext";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

type AgentKey = "veilleur" | "analyste" | "stratege" | "redacteur";

function ChatPageInner() {
  const searchParams = useSearchParams();
  const { activeProfile } = useProfile();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [agent, setAgent] = useState<AgentKey>("analyste");
  const [texteUid, setTexteUid] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const hasPreFilled = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Pre-fill from URL params
  useEffect(() => {
    const prompt = searchParams.get("prompt");
    const agentParam = searchParams.get("agent");
    const texteUidParam = searchParams.get("texte_uid");
    if (prompt && !hasPreFilled.current) {
      hasPreFilled.current = true;
      setInput(decodeURIComponent(prompt));
      if (agentParam && ["veilleur", "analyste", "stratege", "redacteur"].includes(agentParam)) {
        setAgent(agentParam as AgentKey);
      }
    }
    if (texteUidParam) {
      setTexteUid(texteUidParam);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const now = new Date().toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const userMsg: Message = {
      id: String(Date.now()),
      role: "user",
      content: text,
      timestamp: now,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const body: Record<string, unknown> = { message: text, agent };
      if (activeProfile) {
        body.profile_id = activeProfile.id;
      }
      if (texteUid) {
        body.texte_uid = texteUid;
      }

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      const assistantMsg: Message = {
        id: String(Date.now() + 1),
        role: "assistant",
        content: data.response || "Erreur de réponse.",
        timestamp: new Date().toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now() + 1),
          role: "assistant",
          content: "Erreur de connexion au serveur.",
          timestamp: now,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="font-serif text-3xl font-bold text-dark">Agent IA</h1>
          <p className="mt-1 text-sm text-muted">
            {activeProfile ? (
              <span className="inline-flex items-center gap-1.5">
                <Building2 className="inline h-3.5 w-3.5" />
                Contexte : {activeProfile.name}
                <span className="text-warm">
                  ({activeProfile.sectors.join(", ")})
                </span>
              </span>
            ) : (
              "Posez vos questions sur la réglementation et vos textes suivis"
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {(["veilleur", "analyste", "stratege", "redacteur"] as AgentKey[]).map((a) => (
            <button
              key={a}
              onClick={() => setAgent(a)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                agent === a
                  ? "bg-dark text-white"
                  : "bg-white text-muted hover:bg-cream-dark"
              }`}
            >
              {a.charAt(0).toUpperCase() + a.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Context banner */}
      {texteUid && (
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-warm/10 px-4 py-2">
          <FileText className="h-4 w-4 text-warm" />
          <span className="text-sm font-medium text-warm">
            Contexte : dossier {texteUid}
          </span>
          <button
            onClick={() => setTexteUid(null)}
            className="ml-auto text-xs text-muted hover:text-dark"
          >
            Retirer le contexte
          </button>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto rounded-xl bg-white p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <Bot className="mx-auto h-12 w-12 text-warm/30" />
                <p className="mt-4 text-sm text-muted">
                  Bonjour ! Je suis votre agent {agent === "veilleur" ? "veilleur" : "analyste"}.
                  {activeProfile && (
                    <>
                      <br />
                      <span className="text-warm">
                        Je raisonne dans le contexte de {activeProfile.name}.
                      </span>
                    </>
                  )}
                </p>
                {activeProfile && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs font-medium text-muted">Suggestions :</p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {[
                        "Quels sont les derniers textes impactant nos secteurs ?",
                        "Analyse les menaces en cours",
                        "Qui sont les députés actifs sur nos thématiques ?",
                      ].map((suggestion) => (
                        <button
                          key={suggestion}
                          onClick={() => setInput(suggestion)}
                          className="rounded-full bg-cream px-3 py-1.5 text-xs text-warm transition-colors hover:bg-cream-dark"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {message.role === "assistant" && (
                <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-warm/10">
                  <Bot className="h-4 w-4 text-warm" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  message.role === "user"
                    ? "bg-dark text-white"
                    : "bg-cream text-dark"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="mb-1.5 flex items-center gap-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-warm">
                      LegiX IA
                    </span>
                    {activeProfile && (
                      <span className="text-[10px] text-muted">
                        pour {activeProfile.name}
                      </span>
                    )}
                  </div>
                )}
                <div className="whitespace-pre-line text-sm leading-relaxed">
                  {message.content}
                </div>
                <p
                  className={`mt-2 text-right text-[10px] ${
                    message.role === "user" ? "text-white/50" : "text-muted"
                  }`}
                >
                  {message.timestamp}
                </p>
              </div>
              {message.role === "user" && (
                <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-dark">
                  <User className="h-4 w-4 text-white" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-warm/10">
                <Bot className="h-4 w-4 text-warm" />
              </div>
              <div className="rounded-2xl bg-cream px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-warm" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input bar */}
      <form onSubmit={handleSubmit} className="mt-4">
        <div className="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              activeProfile
                ? `Question pour ${activeProfile.name}...`
                : "Posez une question sur vos textes, alertes ou réglementation..."
            }
            className="flex-1 bg-transparent px-2 text-sm text-dark placeholder:text-muted/50 focus:outline-none"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-dark text-white transition-colors hover:bg-dark/80 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-warm" /></div>}>
      <ChatPageInner />
    </Suspense>
  );
}
