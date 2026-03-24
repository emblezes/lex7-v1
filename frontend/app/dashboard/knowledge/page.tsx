"use client";

import { useEffect, useState, useCallback } from "react";
import { useProfile } from "../ProfileContext";
import {
  Upload,
  FileText,
  Search,
  Trash2,
  Plus,
  BookOpen,
  Tag,
  Clock,
} from "lucide-react";

interface Document {
  id: number;
  title: string;
  doc_type: string;
  summary: string | null;
  themes: string[];
  file_name: string | null;
  created_at: string;
}

interface SearchResult {
  document_id: number;
  document_title: string;
  doc_type: string;
  chunk_text: string;
  score: number;
  themes: string[];
}

interface KBStats {
  total_documents: number;
  documents_by_type: Record<string, number>;
  total_chunks: number;
  themes_covered: string[];
}

const DOC_TYPES = [
  { value: "position_paper", label: "Position paper" },
  { value: "internal_note", label: "Note interne" },
  { value: "email", label: "Email" },
  { value: "communication", label: "Communication" },
  { value: "rapport", label: "Rapport" },
  { value: "presentation", label: "Presentation" },
];

export default function KnowledgePage() {
  const { activeProfile } = useProfile();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [showText, setShowText] = useState(false);
  const [textTitle, setTextTitle] = useState("");
  const [textContent, setTextContent] = useState("");
  const [textType, setTextType] = useState("internal_note");
  const [uploadType, setUploadType] = useState("rapport");

  const profileId = activeProfile?.id;

  const loadData = useCallback(async () => {
    if (!profileId) return;
    const [docsRes, statsRes] = await Promise.all([
      fetch(`/api/knowledge/profiles/${profileId}/documents`),
      fetch(`/api/knowledge/profiles/${profileId}/stats`),
    ]);
    if (docsRes.ok) setDocuments(await docsRes.json());
    if (statsRes.ok) setStats(await statsRes.json());
  }, [profileId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearch = async () => {
    if (!profileId || !searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await fetch(
        `/api/knowledge/profiles/${profileId}/search?q=${encodeURIComponent(searchQuery)}&top_k=8`
      );
      if (res.ok) setSearchResults(await res.json());
    } finally {
      setSearching(false);
    }
  };

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!profileId) return;
    const formData = new FormData(e.currentTarget);
    formData.set("doc_type", uploadType);
    setUploading(true);
    try {
      const res = await fetch(
        `/api/knowledge/profiles/${profileId}/documents/upload`,
        { method: "POST", body: formData }
      );
      if (res.ok) {
        setShowUpload(false);
        loadData();
      }
    } finally {
      setUploading(false);
    }
  };

  const handleTextIngest = async () => {
    if (!profileId || !textTitle || !textContent) return;
    setUploading(true);
    try {
      const res = await fetch(
        `/api/knowledge/profiles/${profileId}/documents/text`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: textTitle,
            doc_type: textType,
            content: textContent,
          }),
        }
      );
      if (res.ok) {
        setShowText(false);
        setTextTitle("");
        setTextContent("");
        loadData();
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: number) => {
    if (!profileId || !confirm("Supprimer ce document ?")) return;
    await fetch(`/api/knowledge/profiles/${profileId}/documents/${docId}`, {
      method: "DELETE",
    });
    loadData();
  };

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-dark flex items-center gap-3">
            <BookOpen size={28} />
            Base de connaissances
          </h1>
          <p className="text-dark/50 mt-1">
            Documents internes pour personnaliser les analyses et livrables
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowText(true)}
            className="flex items-center gap-2 px-4 py-2 border border-dark/10 rounded-lg hover:bg-dark/5 text-sm"
          >
            <Plus size={16} />
            Coller du texte
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 px-4 py-2 bg-dark text-cream rounded-lg hover:bg-dark/90 text-sm"
          >
            <Upload size={16} />
            Importer un fichier
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-dark/5 p-4">
            <p className="text-2xl font-bold text-dark">
              {stats.total_documents}
            </p>
            <p className="text-sm text-dark/50">Documents</p>
          </div>
          <div className="bg-white rounded-xl border border-dark/5 p-4">
            <p className="text-2xl font-bold text-dark">
              {stats.total_chunks}
            </p>
            <p className="text-sm text-dark/50">Passages indexes</p>
          </div>
          <div className="bg-white rounded-xl border border-dark/5 p-4">
            <p className="text-2xl font-bold text-dark">
              {Object.keys(stats.documents_by_type).length}
            </p>
            <p className="text-sm text-dark/50">Types de docs</p>
          </div>
          <div className="bg-white rounded-xl border border-dark/5 p-4">
            <p className="text-2xl font-bold text-dark">
              {stats.themes_covered.length}
            </p>
            <p className="text-sm text-dark/50">Themes couverts</p>
          </div>
        </div>
      )}

      {/* Recherche semantique */}
      <div className="bg-white rounded-xl border border-dark/5 p-6 mb-8">
        <h2 className="font-semibold text-dark mb-3 flex items-center gap-2">
          <Search size={18} />
          Recherche dans vos documents
        </h2>
        <div className="flex gap-3">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Quelle est notre position sur les PFAS ?"
            className="flex-1 px-4 py-2.5 border border-dark/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-warm/50"
          />
          <button
            onClick={handleSearch}
            disabled={searching}
            className="px-5 py-2.5 bg-dark text-cream rounded-lg text-sm hover:bg-dark/90 disabled:opacity-50"
          >
            {searching ? "Recherche..." : "Rechercher"}
          </button>
        </div>
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-3">
            {searchResults.map((r, i) => (
              <div
                key={i}
                className="p-4 bg-cream/50 rounded-lg border border-dark/5"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-dark">
                    {r.document_title}
                  </span>
                  <span className="text-xs text-dark/40">
                    score: {(r.score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-sm text-dark/70 line-clamp-3">
                  {r.chunk_text}
                </p>
                <div className="flex gap-2 mt-2">
                  {r.themes.map((t) => (
                    <span
                      key={t}
                      className="text-xs px-2 py-0.5 bg-warm/10 text-warm rounded"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Liste des documents */}
      <div className="space-y-3">
        <h2 className="font-semibold text-dark">
          Documents ({documents.length})
        </h2>
        {documents.length === 0 ? (
          <div className="bg-white rounded-xl border border-dark/5 p-12 text-center">
            <FileText size={48} className="mx-auto text-dark/20 mb-4" />
            <p className="text-dark/50">
              Aucun document. Importez vos position papers, notes internes,
              emails...
            </p>
          </div>
        ) : (
          documents.map((doc) => (
            <div
              key={doc.id}
              className="bg-white rounded-xl border border-dark/5 p-5 flex items-start justify-between"
            >
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <FileText size={16} className="text-warm" />
                  <span className="font-medium text-dark">{doc.title}</span>
                  <span className="text-xs px-2 py-0.5 bg-dark/5 rounded">
                    {doc.doc_type}
                  </span>
                </div>
                {doc.summary && (
                  <p className="text-sm text-dark/60 ml-7 line-clamp-2">
                    {doc.summary}
                  </p>
                )}
                <div className="flex items-center gap-3 mt-2 ml-7">
                  {doc.themes.map((t) => (
                    <span
                      key={t}
                      className="text-xs px-2 py-0.5 bg-warm/10 text-warm rounded flex items-center gap-1"
                    >
                      <Tag size={10} />
                      {t}
                    </span>
                  ))}
                  <span className="text-xs text-dark/30 flex items-center gap-1">
                    <Clock size={10} />
                    {new Date(doc.created_at).toLocaleDateString("fr-FR")}
                  </span>
                </div>
              </div>
              <button
                onClick={() => handleDelete(doc.id)}
                className="p-2 text-dark/30 hover:text-threat"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Modal Upload */}
      {showUpload && (
        <div className="fixed inset-0 bg-dark/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-8 w-full max-w-lg">
            <h3 className="text-lg font-semibold mb-4">Importer un fichier</h3>
            <form onSubmit={handleUpload}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">
                  Type de document
                </label>
                <select
                  value={uploadType}
                  onChange={(e) => setUploadType(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  {DOC_TYPES.map((dt) => (
                    <option key={dt.value} value={dt.value}>
                      {dt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">
                  Fichier (PDF, DOCX, TXT, MD, HTML)
                </label>
                <input
                  type="file"
                  name="file"
                  accept=".pdf,.docx,.doc,.txt,.md,.html"
                  required
                  className="w-full text-sm"
                />
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowUpload(false)}
                  className="px-4 py-2 text-sm border rounded-lg"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-5 py-2 bg-dark text-cream rounded-lg text-sm disabled:opacity-50"
                >
                  {uploading ? "Import en cours..." : "Importer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Texte */}
      {showText && (
        <div className="fixed inset-0 bg-dark/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-8 w-full max-w-2xl">
            <h3 className="text-lg font-semibold mb-4">Coller du texte</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Titre</label>
                <input
                  value={textTitle}
                  onChange={(e) => setTextTitle(e.target.value)}
                  placeholder="Titre du document"
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Type</label>
                <select
                  value={textType}
                  onChange={(e) => setTextType(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  {DOC_TYPES.map((dt) => (
                    <option key={dt.value} value={dt.value}>
                      {dt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Contenu
                </label>
                <textarea
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  rows={10}
                  placeholder="Collez votre texte ici (email, note, position paper...)"
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowText(false)}
                  className="px-4 py-2 text-sm border rounded-lg"
                >
                  Annuler
                </button>
                <button
                  onClick={handleTextIngest}
                  disabled={uploading || !textTitle || !textContent}
                  className="px-5 py-2 bg-dark text-cream rounded-lg text-sm disabled:opacity-50"
                >
                  {uploading ? "Ingestion..." : "Ingerer"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
