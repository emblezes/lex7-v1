"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Identifiants incorrects");
        return;
      }
      const data = await res.json();
      localStorage.setItem("legix_token", data.access_token);
      router.push("/dashboard");
    } catch {
      setError("Erreur de connexion au serveur");
    } finally {
      setLoading(false);
    }
  };

  // Mode demo — skip auth
  const handleDemo = () => {
    localStorage.setItem("legix_token", "demo");
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-dark tracking-tight">
            Legi<span className="text-warm">X</span>
          </h1>
          <p className="text-dark/50 mt-2">Intelligence reglementaire active</p>
        </div>

        <div className="bg-white rounded-2xl border border-dark/5 p-8 shadow-sm">
          <h2 className="text-lg font-semibold text-dark mb-6">Connexion</h2>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-dark/70 mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="votre@email.com"
                className="w-full px-4 py-2.5 border border-dark/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-warm/50"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-dark/70 mb-1">
                Mot de passe
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-2.5 border border-dark/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-warm/50"
                required
              />
            </div>

            {error && (
              <p className="text-sm text-threat bg-threat/5 px-3 py-2 rounded-lg">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-dark text-cream rounded-lg font-medium hover:bg-dark/90 disabled:opacity-50"
            >
              {loading ? "Connexion..." : "Se connecter"}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-dark/5">
            <button
              onClick={handleDemo}
              className="w-full py-2.5 border border-dark/10 rounded-lg text-sm text-dark/70 hover:bg-dark/5"
            >
              Acceder a la demo (sans compte)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
