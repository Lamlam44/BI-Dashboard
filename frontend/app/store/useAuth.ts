"use client";

import { create } from "zustand";
import { API_BASE_URL } from '../lib/api';

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  region: string | null;
  store_key: number | null;
  display_name: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  loadFromStorage: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: null,
  user: null,
  loading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        set({ loading: false, error: body.detail || "Login failed" });
        return false;
      }
      const data = await res.json();
      localStorage.setItem("bi_token", data.access_token);
      localStorage.setItem("bi_user", JSON.stringify(data.user));
      set({ token: data.access_token, user: data.user, loading: false, error: null });
      return true;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Network error";
      set({ loading: false, error: msg });
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem("bi_token");
    localStorage.removeItem("bi_user");
    set({ token: null, user: null, error: null });
  },

  loadFromStorage: () => {
    try {
      const token = localStorage.getItem("bi_token");
      const raw = localStorage.getItem("bi_user");
      if (token && raw) {
        // Decode JWT payload and check expiry (client-side fast check)
        try {
          const parts = token.split('.');
          if (parts.length === 3) {
            const padding = '='.repeat((4 - (parts[1].length % 4)) % 4);
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/') + padding));
            if (payload.exp && payload.exp < Date.now() / 1000) {
              // Token expired — clear and force re-login
              localStorage.removeItem("bi_token");
              localStorage.removeItem("bi_user");
              return;
            }
          }
        } catch {
          // Malformed token — discard it
          localStorage.removeItem("bi_token");
          localStorage.removeItem("bi_user");
          return;
        }
        const user = JSON.parse(raw) as AuthUser;
        set({ token, user });
      }
    } catch {
      // corrupted storage — ignore
    }
  },
}));
