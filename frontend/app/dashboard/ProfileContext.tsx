"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { fetchProfileDetail, type ProfileDetail } from "@/lib/api";

const API = "";

export interface Profile {
  id: number;
  name: string;
  email: string;
  sectors: string[];
  context_note: string;
  is_active: boolean;
  stats?: {
    total_alertes: number;
    non_lues: number;
    urgentes: number;
  };
}

interface ProfileContextType {
  profiles: Profile[];
  activeProfile: Profile | null;
  profileDetail: ProfileDetail | null;
  setActiveProfileId: (id: number | null) => void;
  loading: boolean;
}

const ProfileContext = createContext<ProfileContextType>({
  profiles: [],
  activeProfile: null,
  profileDetail: null,
  setActiveProfileId: () => {},
  loading: true,
});

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<number | null>(null);
  const [profileDetail, setProfileDetail] = useState<ProfileDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("legix_token");
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    fetch(`${API}/api/profiles`, { headers })
      .then((r) => r.json())
      .then(async (data) => {
        const list = Array.isArray(data) ? data : [];
        setProfiles(list);
        // Restaurer depuis localStorage ou prendre le premier
        const saved = localStorage.getItem("legix_profile_id");
        let selectedId: number | null = null;
        if (saved && list.find((p: Profile) => p.id === parseInt(saved))) {
          selectedId = parseInt(saved);
        } else if (list.length > 0) {
          selectedId = list[0].id;
        }
        setActiveProfileId(selectedId);
        // Fetch detail immediatement pour eviter le flash
        if (selectedId !== null) {
          try {
            const detail = await fetchProfileDetail(selectedId);
            setProfileDetail(detail);
          } catch {
            /* ignore */
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Re-fetch detail quand le profil actif change
  useEffect(() => {
    if (activeProfileId !== null) {
      localStorage.setItem("legix_profile_id", String(activeProfileId));
      fetchProfileDetail(activeProfileId)
        .then(setProfileDetail)
        .catch(() => setProfileDetail(null));
    } else {
      setProfileDetail(null);
    }
  }, [activeProfileId]);

  const activeProfile =
    profiles.find((p) => p.id === activeProfileId) ?? null;

  return (
    <ProfileContext.Provider
      value={{ profiles, activeProfile, profileDetail, setActiveProfileId, loading }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  return useContext(ProfileContext);
}
