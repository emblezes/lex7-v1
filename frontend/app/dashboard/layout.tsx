"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Sun,
  FolderOpen,
  CheckSquare,
  Users,
  MessageSquare,
  Settings,
  ChevronDown,
  Radar,
  Newspaper,
  BookOpen,
} from "lucide-react";
import { ProfileProvider, useProfile } from "./ProfileContext";

const navItems = [
  { label: "Aujourd'hui", href: "/dashboard", icon: Sun },
  { label: "Anticipation", href: "/dashboard/anticipation", icon: Radar },
  { label: "Dossiers", href: "/dashboard/dossiers", icon: FolderOpen },
  { label: "Acteurs", href: "/dashboard/acteurs", icon: Users },
  { label: "Presse", href: "/dashboard/presse", icon: Newspaper },
  { label: "Actions", href: "/dashboard/actions", icon: CheckSquare },
];

const secondaryItems = [
  { label: "Agent IA", href: "/dashboard/chat", icon: MessageSquare },
  { label: "Documents", href: "/dashboard/knowledge", icon: BookOpen },
];

function ProfileSelector() {
  const { profiles, activeProfile, profileDetail, setActiveProfileId } = useProfile();

  if (profiles.length === 0) return null;

  return (
    <div className="px-3 pb-2">
      <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-muted">
        Client actif
      </label>
      <div className="relative">
        <select
          value={activeProfile?.id ?? ""}
          onChange={(e) => setActiveProfileId(parseInt(e.target.value))}
          className="w-full appearance-none rounded-lg border border-border bg-cream px-3 py-2 pr-8 text-sm font-medium text-dark transition-colors hover:border-warm focus:border-warm focus:outline-none focus:ring-1 focus:ring-warm"
        >
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      </div>
      {profileDetail?.stats && (
        <div className="mt-1.5 flex gap-2 text-xs text-muted">
          <span>{profileDetail.stats.total_alertes} alertes</span>
          <span>-</span>
          <span className="text-threat">
            {profileDetail.stats.urgentes} urgentes
          </span>
        </div>
      )}
    </div>
  );
}

function SidebarContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-border bg-white">
        {/* Logo */}
        <div className="flex h-16 items-center px-6">
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="font-serif text-2xl font-bold text-dark">
              LegiX
            </span>
          </Link>
        </div>

        {/* Selecteur profil */}
        <ProfileSelector />

        {/* Navigation principale */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-dark text-white"
                    : "text-muted hover:bg-cream hover:text-dark"
                }`}
              >
                <Icon className="h-5 w-5 flex-shrink-0" />
                {item.label}
              </Link>
            );
          })}

          {/* Separateur */}
          <div className="my-3 border-t border-border" />

          {secondaryItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-dark text-white"
                    : "text-muted hover:bg-cream hover:text-dark"
                }`}
              >
                <Icon className="h-5 w-5 flex-shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="border-t border-border px-3 py-4">
          <Link
            href="/dashboard/settings"
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              pathname === "/dashboard/settings"
                ? "bg-dark text-white"
                : "text-muted hover:bg-cream hover:text-dark"
            }`}
          >
            <Settings className="h-5 w-5 flex-shrink-0" />
            Parametres
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-64 min-h-screen flex-1 bg-cream p-8">
        {children}
      </main>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProfileProvider>
      <SidebarContent>{children}</SidebarContent>
    </ProfileProvider>
  );
}
