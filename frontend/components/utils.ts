export function formatEur(n: number | null | undefined): string {
  if (!n) return "-";
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} Md\u20ac`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)} M\u20ac`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} K\u20ac`;
  return `${n.toFixed(0)} \u20ac`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "a l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `il y a ${hours}h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days}j`;
}

export const levelBorder: Record<string, string> = {
  critical: "border-l-red-600",
  high: "border-l-orange-500",
  medium: "border-l-amber-400",
  low: "border-l-stone-300",
};

export const levelColors: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-orange-500 text-white",
  medium: "bg-amber-400 text-dark",
  low: "bg-stone-200 text-stone-600",
};

export const levelLabels: Record<string, string> = {
  critical: "Critique",
  high: "Eleve",
  medium: "Moyen",
  low: "Faible",
};
