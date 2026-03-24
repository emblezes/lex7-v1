"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  X,
  Download,
  Mail,
  Send,
  Copy,
  Check,
  Loader2,
  Pencil,
  Eye,
  FileText,
  Paperclip,
  Maximize2,
  Minimize2,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Heading1,
  Heading2,
  List,
  ListOrdered,
  AlignLeft,
  AlignCenter,
  Undo2,
  Redo2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import UnderlineExt from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Placeholder from "@tiptap/extension-placeholder";
import {
  streamGenerateLivrable,
  updateLivrable,
  sendLivrableEmail,
  type StreamEvent,
  type LivrableOut,
  type ActionTask,
  type EmailPrepared,
} from "@/lib/api";

/* ── Types ── */

type WorkspaceStep = "idle" | "generating" | "editing" | "sending";

interface DocumentWorkspaceProps {
  action: ActionTask;
  livrableType: string;
  onClose: () => void;
  onLivrableReady?: (livrable: LivrableOut) => void;
  existingLivrable?: LivrableOut | null;
}

/* ── Markdown → HTML conversion (pour TipTap) ── */

function markdownToHtml(md: string): string {
  let html = md;
  // Headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Bold & italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Unordered lists
  html = html.replace(/^[-*] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
  // Horizontal rule
  html = html.replace(/^---$/gm, "<hr>");
  // Paragraphs (lines not already wrapped)
  html = html
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      if (
        !trimmed ||
        trimmed.startsWith("<h") ||
        trimmed.startsWith("<ul") ||
        trimmed.startsWith("<ol") ||
        trimmed.startsWith("<li") ||
        trimmed.startsWith("<hr")
      )
        return trimmed;
      return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
  return html;
}

function htmlToMarkdown(html: string): string {
  let md = html;
  md = md.replace(/<h1>(.*?)<\/h1>/gi, "# $1\n\n");
  md = md.replace(/<h2>(.*?)<\/h2>/gi, "## $1\n\n");
  md = md.replace(/<h3>(.*?)<\/h3>/gi, "### $1\n\n");
  md = md.replace(/<strong>(.*?)<\/strong>/gi, "**$1**");
  md = md.replace(/<em>(.*?)<\/em>/gi, "*$1*");
  md = md.replace(/<u>(.*?)<\/u>/gi, "$1");
  md = md.replace(/<li>(.*?)<\/li>/gi, "- $1\n");
  md = md.replace(/<\/?ul>/gi, "\n");
  md = md.replace(/<\/?ol>/gi, "\n");
  md = md.replace(/<hr\s*\/?>/gi, "---\n\n");
  md = md.replace(/<br\s*\/?>/gi, "\n");
  md = md.replace(/<p>(.*?)<\/p>/gi, "$1\n\n");
  md = md.replace(/<\/?[^>]+(>|$)/g, "");
  md = md.replace(/\n{3,}/g, "\n\n");
  return md.trim();
}

/* ── TipTap Toolbar ── */

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;

  const btnClass = (active: boolean) =>
    `rounded p-1.5 transition ${
      active
        ? "bg-dark text-white"
        : "text-muted hover:bg-stone-100 hover:text-dark"
    }`;

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-border bg-stone-50 px-4 py-1.5">
      <button
        onClick={() => editor.chain().focus().undo().run()}
        className={btnClass(false)}
        title="Annuler"
      >
        <Undo2 className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().redo().run()}
        className={btnClass(false)}
        title="Retablir"
      >
        <Redo2 className="h-4 w-4" />
      </button>

      <div className="mx-1.5 h-5 w-px bg-border" />

      <button
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        className={btnClass(editor.isActive("heading", { level: 1 }))}
        title="Titre 1"
      >
        <Heading1 className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        className={btnClass(editor.isActive("heading", { level: 2 }))}
        title="Titre 2"
      >
        <Heading2 className="h-4 w-4" />
      </button>

      <div className="mx-1.5 h-5 w-px bg-border" />

      <button
        onClick={() => editor.chain().focus().toggleBold().run()}
        className={btnClass(editor.isActive("bold"))}
        title="Gras"
      >
        <Bold className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().toggleItalic().run()}
        className={btnClass(editor.isActive("italic"))}
        title="Italique"
      >
        <Italic className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().toggleUnderline().run()}
        className={btnClass(editor.isActive("underline"))}
        title="Souligne"
      >
        <UnderlineIcon className="h-4 w-4" />
      </button>

      <div className="mx-1.5 h-5 w-px bg-border" />

      <button
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        className={btnClass(editor.isActive("bulletList"))}
        title="Liste a puces"
      >
        <List className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        className={btnClass(editor.isActive("orderedList"))}
        title="Liste numerotee"
      >
        <ListOrdered className="h-4 w-4" />
      </button>

      <div className="mx-1.5 h-5 w-px bg-border" />

      <button
        onClick={() => editor.chain().focus().setTextAlign("left").run()}
        className={btnClass(editor.isActive({ textAlign: "left" }))}
        title="Aligner a gauche"
      >
        <AlignLeft className="h-4 w-4" />
      </button>
      <button
        onClick={() => editor.chain().focus().setTextAlign("center").run()}
        className={btnClass(editor.isActive({ textAlign: "center" }))}
        title="Centrer"
      >
        <AlignCenter className="h-4 w-4" />
      </button>
    </div>
  );
}

/* ── Composant principal ── */

export default function DocumentWorkspace({
  action,
  livrableType,
  onClose,
  onLivrableReady,
  existingLivrable,
}: DocumentWorkspaceProps) {
  const [step, setStep] = useState<WorkspaceStep>(
    existingLivrable?.content ? "editing" : "idle",
  );
  const [content, setContent] = useState(existingLivrable?.content || "");
  const [livrableId, setLivrableId] = useState<number | null>(
    existingLivrable?.id || null,
  );
  const [title, setTitle] = useState(existingLivrable?.title || "");
  const [isPreview, setIsPreview] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [emailTo, setEmailTo] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailPrepared, setEmailPrepared] = useState<EmailPrepared | null>(
    null,
  );
  const [sendingEmail, setSendingEmail] = useState(false);
  const [showEmailPanel, setShowEmailPanel] = useState(false);

  const streamRef = useRef<AbortController | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // TipTap editor — immediatelyRender: false to avoid SSR crash
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      UnderlineExt,
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Placeholder.configure({ placeholder: "Le document sera genere ici..." }),
    ],
    content: existingLivrable?.content
      ? markdownToHtml(existingLivrable.content)
      : "",
    editorProps: {
      attributes: {
        class:
          "prose prose-stone prose-sm sm:prose-base max-w-none px-12 py-8 min-h-full focus:outline-none " +
          "[&_h1]:font-serif [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-stone-900 [&_h1]:mb-4 [&_h1]:mt-6 " +
          "[&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-stone-800 [&_h2]:mb-3 [&_h2]:mt-5 " +
          "[&_h3]:font-serif [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-stone-700 [&_h3]:mb-2 [&_h3]:mt-4 " +
          "[&_p]:text-stone-700 [&_p]:leading-relaxed [&_p]:mb-3 " +
          "[&_strong]:text-stone-900 [&_strong]:font-semibold " +
          "[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:mb-3 " +
          "[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:mb-3 " +
          "[&_li]:text-stone-700 [&_li]:mb-1 " +
          "[&_hr]:border-stone-200 [&_hr]:my-6",
      },
    },
    onUpdate: ({ editor: ed }) => {
      setContent(htmlToMarkdown(ed.getHTML()));
    },
  });

  // Auto-start generation if no existing content
  useEffect(() => {
    if (!existingLivrable?.content && step === "idle") {
      handleGenerate();
    }
    return () => {
      streamRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll during generation
  useEffect(() => {
    if (step === "generating" && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [content, step]);

  // Sync content to editor when generation finishes
  useEffect(() => {
    if (step === "editing" && editor && content) {
      const currentEditorMd = htmlToMarkdown(editor.getHTML());
      // Only update if significantly different (avoid loop)
      if (
        Math.abs(currentEditorMd.length - content.length) > 10 ||
        !currentEditorMd
      ) {
        editor.commands.setContent(markdownToHtml(content));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const handleGenerate = useCallback(() => {
    setStep("generating");
    setContent("");
    setIsPreview(true);
    setStatusMessage(null);
    setErrorMessage(null);

    const controller = streamGenerateLivrable(
      action.id,
      livrableType,
      (event: StreamEvent) => {
        switch (event.type) {
          case "init":
            setLivrableId(event.livrable_id || null);
            setTitle(event.title || "");
            setStatusMessage(null);
            break;
          case "delta":
            setContent((prev) => prev + (event.text || ""));
            setStatusMessage(null);
            break;
          case "done":
            setStep("editing");
            setStatusMessage(null);
            if (event.livrable_id) {
              setLivrableId(event.livrable_id);
            }
            break;
          case "error":
            setStep("editing");
            setErrorMessage(
              event.message?.includes("overloaded")
                ? "L'API IA est temporairement surchargee. Reessayez dans quelques secondes."
                : event.message || "Erreur lors de la generation",
            );
            break;
          case "status":
            setStatusMessage(event.message || null);
            break;
        }
      },
    );

    streamRef.current = controller;
  }, [action.id, livrableType]);

  const handleSave = async () => {
    if (!livrableId) return;
    setSaving(true);
    try {
      const updated = await updateLivrable(livrableId, { content, title });
      onLivrableReady?.(updated);
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrepareEmail = async () => {
    if (!livrableId || !emailTo) return;
    setSendingEmail(true);
    try {
      const prepared = await sendLivrableEmail(
        livrableId,
        emailTo,
        emailSubject || title,
      );
      setEmailPrepared(prepared);
    } catch {
      /* ignore */
    }
    setSendingEmail(false);
  };

  const handleDownloadPdf = () => {
    if (emailPrepared?.pdf_base64) {
      const link = document.createElement("a");
      link.href = `data:application/pdf;base64,${emailPrepared.pdf_base64}`;
      link.download = emailPrepared.pdf_filename;
      link.click();
    } else if (livrableId) {
      window.open(`/api/livrables/${livrableId}/pdf`, "_blank");
    }
  };

  const handleOpenMailClient = () => {
    if (emailPrepared?.mailto_link) {
      window.open(emailPrepared.mailto_link, "_blank");
    }
  };

  const typeLabels: Record<string, string> = {
    note_comex: "Note COMEX",
    email: "Email parlementaire",
    amendement: "Contre-amendement",
    fiche_position: "Fiche de position",
  };

  const containerClass = isFullscreen
    ? "fixed inset-0 z-50 bg-white"
    : "fixed inset-4 z-50 rounded-2xl border border-border bg-white shadow-2xl";

  return (
    <>
      {/* Backdrop */}
      {!isFullscreen && (
        <div
          className="fixed inset-0 z-40 bg-dark/40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <div className={containerClass}>
        <div className="flex h-full flex-col">
          {/* ── Toolbar ── */}
          <div className="flex items-center justify-between border-b border-border px-6 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-warm/10">
                <FileText className="h-5 w-5 text-warm" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-dark">
                  {typeLabels[livrableType] || livrableType}
                </h2>
                <p className="text-xs text-muted">{action.label}</p>
              </div>
              {step === "generating" && (
                <div className="flex items-center gap-2 rounded-full bg-warm/10 px-3 py-1">
                  <div className="h-2 w-2 animate-pulse rounded-full bg-warm" />
                  <span className="text-xs font-medium text-warm">
                    Redaction en cours...
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Mode toggle */}
              {step === "editing" && (
                <div className="flex rounded-lg border border-border">
                  <button
                    onClick={() => setIsPreview(false)}
                    className={`flex items-center gap-1.5 rounded-l-lg px-3 py-1.5 text-xs font-medium transition ${
                      !isPreview
                        ? "bg-dark text-white"
                        : "text-muted hover:bg-cream"
                    }`}
                  >
                    <Pencil className="h-3 w-3" />
                    Editer
                  </button>
                  <button
                    onClick={() => setIsPreview(true)}
                    className={`flex items-center gap-1.5 rounded-r-lg px-3 py-1.5 text-xs font-medium transition ${
                      isPreview
                        ? "bg-dark text-white"
                        : "text-muted hover:bg-cream"
                    }`}
                  >
                    <Eye className="h-3 w-3" />
                    Document
                  </button>
                </div>
              )}

              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-warm hover:text-warm"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                {copied ? "Copie" : "Copier"}
              </button>

              <button
                onClick={handleDownloadPdf}
                disabled={!content}
                className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-warm hover:text-warm disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
                PDF
              </button>

              <button
                onClick={() => setShowEmailPanel(!showEmailPanel)}
                disabled={!content}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  showEmailPanel
                    ? "bg-warm text-white"
                    : "border border-border text-muted hover:border-warm hover:text-warm"
                } disabled:opacity-50`}
              >
                <Mail className="h-3.5 w-3.5" />
                Envoyer
              </button>

              {step === "editing" && (
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-lg bg-dark px-4 py-1.5 text-xs font-medium text-white transition hover:bg-dark/80 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Check className="h-3.5 w-3.5" />
                  )}
                  Sauvegarder
                </button>
              )}

              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="rounded-lg p-1.5 text-muted hover:bg-cream"
              >
                {isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </button>

              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-muted hover:bg-cream hover:text-dark"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* ── TipTap Toolbar (edit mode only) ── */}
          {step === "editing" && !isPreview && editor && <EditorToolbar editor={editor} />}

          {/* ── Content area ── */}
          <div className="flex flex-1 overflow-hidden">
            <div className="flex-1 overflow-hidden">
              {step === "generating" ? (
                /* Streaming view — rendered markdown en temps reel */
                <div
                  ref={contentRef}
                  className="h-full overflow-y-auto bg-white"
                >
                  <div className="mx-auto max-w-3xl px-12 py-8">
                    {/* Status/retry message */}
                    {statusMessage && (
                      <div className="mb-4 flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3">
                        <Loader2 className="h-4 w-4 animate-spin text-amber-500" />
                        <span className="text-sm text-amber-700">{statusMessage}</span>
                      </div>
                    )}
                    {errorMessage && !content && (
                      <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3">
                        <p className="text-sm font-medium text-red-700">Erreur</p>
                        <p className="mt-1 text-sm text-red-600">{errorMessage}</p>
                        <button
                          onClick={handleGenerate}
                          className="mt-2 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
                        >
                          Reessayer
                        </button>
                      </div>
                    )}
                    <div
                      className={
                        "prose prose-stone prose-sm sm:prose-base max-w-none " +
                        "[&_h1]:font-serif [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-stone-900 [&_h1]:mb-4 [&_h1]:mt-6 " +
                        "[&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-stone-800 [&_h2]:mb-3 [&_h2]:mt-5 " +
                        "[&_h3]:font-serif [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-stone-700 [&_h3]:mb-2 [&_h3]:mt-4 " +
                        "[&_p]:text-stone-700 [&_p]:leading-relaxed [&_p]:mb-3 " +
                        "[&_strong]:text-stone-900 [&_strong]:font-semibold " +
                        "[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:mb-3 " +
                        "[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:mb-3 " +
                        "[&_li]:text-stone-700 [&_li]:mb-1 " +
                        "[&_hr]:border-stone-200 [&_hr]:my-6 " +
                        "[&_table]:w-full [&_table]:border-collapse [&_th]:bg-stone-50 [&_th]:border [&_th]:border-stone-200 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-sm [&_th]:font-semibold " +
                        "[&_td]:border [&_td]:border-stone-200 [&_td]:px-3 [&_td]:py-2 [&_td]:text-sm"
                      }
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {content}
                      </ReactMarkdown>
                      <span className="inline-block h-5 w-0.5 animate-pulse bg-warm" />
                    </div>
                  </div>
                </div>
              ) : isPreview ? (
                /* Document preview — rendered markdown */
                <div className="h-full overflow-y-auto bg-white">
                  <div className="mx-auto max-w-3xl px-12 py-8">
                    <div
                      className={
                        "prose prose-stone prose-sm sm:prose-base max-w-none " +
                        "[&_h1]:font-serif [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-stone-900 [&_h1]:mb-4 [&_h1]:mt-6 " +
                        "[&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-stone-800 [&_h2]:mb-3 [&_h2]:mt-5 " +
                        "[&_h3]:font-serif [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-stone-700 [&_h3]:mb-2 [&_h3]:mt-4 " +
                        "[&_p]:text-stone-700 [&_p]:leading-relaxed [&_p]:mb-3 " +
                        "[&_strong]:text-stone-900 [&_strong]:font-semibold " +
                        "[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:mb-3 " +
                        "[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:mb-3 " +
                        "[&_li]:text-stone-700 [&_li]:mb-1 " +
                        "[&_hr]:border-stone-200 [&_hr]:my-6 " +
                        "[&_table]:w-full [&_table]:border-collapse [&_th]:bg-stone-50 [&_th]:border [&_th]:border-stone-200 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-sm [&_th]:font-semibold " +
                        "[&_td]:border [&_td]:border-stone-200 [&_td]:px-3 [&_td]:py-2 [&_td]:text-sm"
                      }
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {content || "*Aucun contenu*"}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                /* TipTap WYSIWYG editor */
                <div className="h-full overflow-y-auto bg-white">
                  <div className="mx-auto max-w-3xl">
                    <EditorContent editor={editor} />
                  </div>
                </div>
              )}
            </div>

            {/* ── Email panel ── */}
            {showEmailPanel && (
              <div className="w-96 border-l border-border bg-cream/30 p-6 overflow-y-auto">
                <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-dark">
                  <Mail className="h-4 w-4 text-warm" />
                  Envoyer par email
                </h3>

                {!emailPrepared ? (
                  <div className="space-y-4">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted">
                        Destinataire
                      </label>
                      <input
                        type="email"
                        value={emailTo}
                        onChange={(e) => setEmailTo(e.target.value)}
                        placeholder="nom@assemblee-nationale.fr"
                        className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-dark focus:border-warm focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted">
                        Objet
                      </label>
                      <input
                        type="text"
                        value={emailSubject || title}
                        onChange={(e) => setEmailSubject(e.target.value)}
                        className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-dark focus:border-warm focus:outline-none"
                      />
                    </div>
                    <div className="rounded-lg border border-border bg-white p-3">
                      <div className="flex items-center gap-2 text-xs text-muted">
                        <Paperclip className="h-3.5 w-3.5" />
                        <span>
                          Piece jointe : {title || "document"}.pdf
                        </span>
                      </div>
                    </div>
                    <div className="rounded-lg bg-stone-50 p-3">
                      <p className="text-xs text-muted mb-2 font-medium">
                        Apercu du corps :
                      </p>
                      <p className="text-xs text-dark whitespace-pre-line">
                        {content
                          .split("\n")
                          .filter(
                            (l) => l.trim() && !l.startsWith("#"),
                          )
                          .slice(0, 3)
                          .join("\n")}
                        {"\n\n"}[Document complet en piece jointe]
                      </p>
                    </div>
                    <button
                      onClick={handlePrepareEmail}
                      disabled={!emailTo || sendingEmail}
                      className="flex w-full items-center justify-center gap-2 rounded-lg bg-dark py-2.5 text-sm font-medium text-white transition hover:bg-dark/80 disabled:opacity-50"
                    >
                      {sendingEmail ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                      Preparer l&apos;envoi
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                      <p className="text-sm font-medium text-emerald-700">
                        Email prepare
                      </p>
                      <p className="mt-1 text-xs text-emerald-600">
                        PDF :{" "}
                        {Math.round(emailPrepared.pdf_size_bytes / 1024)} Ko
                      </p>
                    </div>

                    <button
                      onClick={handleOpenMailClient}
                      className="flex w-full items-center justify-center gap-2 rounded-lg bg-dark py-2.5 text-sm font-medium text-white transition hover:bg-dark/80"
                    >
                      <Mail className="h-4 w-4" />
                      Ouvrir dans mon client mail
                    </button>

                    <button
                      onClick={handleDownloadPdf}
                      className="flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-white py-2.5 text-sm font-medium text-dark transition hover:bg-cream"
                    >
                      <Download className="h-4 w-4" />
                      Telecharger le PDF
                    </button>

                    <button
                      onClick={() => {
                        setEmailPrepared(null);
                        setEmailTo("");
                      }}
                      className="w-full text-center text-xs text-muted hover:text-dark"
                    >
                      Modifier et renvoyer
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Status bar ── */}
          <div className="flex items-center justify-between border-t border-border bg-stone-50 px-6 py-2">
            <div className="flex items-center gap-4 text-xs text-muted">
              <span>{content.length} caracteres</span>
              <span>
                ~
                {Math.ceil(
                  content.split(/\s+/).filter(Boolean).length / 250,
                )}{" "}
                page
                {content.split(/\s+/).filter(Boolean).length > 250 ? "s" : ""}
              </span>
              {livrableId && (
                <span className="text-warm">Livrable #{livrableId}</span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-muted">
              {step === "generating" && (
                <button
                  onClick={() => {
                    streamRef.current?.abort();
                    setStep("editing");
                  }}
                  className="text-red-500 hover:text-red-700"
                >
                  Arreter la generation
                </button>
              )}
              {step === "editing" && (
                <button
                  onClick={handleGenerate}
                  className="text-warm hover:text-dark"
                >
                  Regenerer
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
