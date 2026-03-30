"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Shield, LogIn, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../store/useAuth";

const DEMO_ACCOUNTS = [
  { user: "admin", pw: "admin123", label: "Admin", desc: "Quản trị hệ thống – full access" },
  { user: "ceo", pw: "demo123", label: "CEO", desc: "Ban Giám đốc – xem toàn bộ dữ liệu" },
  { user: "rm_asia", pw: "demo123", label: "RM Asia", desc: "Chỉ xem stores Asia" },
  { user: "rm_europe", pw: "demo123", label: "RM Europe", desc: "Chỉ xem stores Europe" },
  { user: "rm_na", pw: "demo123", label: "RM NA", desc: "Chỉ xem stores North America" },
  { user: "sm_store4", pw: "demo123", label: "SM Store 4", desc: "Chỉ xem Contoso Bellevue" },
];

export default function LoginPage() {
  const router = useRouter();
  const { token, loading, error, login, loadFromStorage } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  // Already logged in → go to dashboard
  useEffect(() => {
    if (token) router.replace("/dashboard");
  }, [token, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await login(username, password);
    if (ok) router.replace("/dashboard");
  };

  const quickLogin = async (user: string, pw: string) => {
    setUsername(user);
    setPassword(pw);
    const ok = await login(user, pw);
    if (ok) router.replace("/dashboard");
  };

  // Don't render if already authenticated (flash prevention)
  if (token) return null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex items-center justify-center p-4">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-500/30 mb-4">
            <Shield size={32} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">BI Dashboard</h1>
          <p className="text-slate-400 text-sm mt-1">Contoso Retail Intelligence System</p>
        </div>

        {/* Login card */}
        <div className="bg-white/[0.07] backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-lg font-semibold text-white mb-6">Đăng nhập</h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Tên đăng nhập
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-2.5 bg-white/10 border border-white/10 rounded-xl text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
                placeholder="Nhập tên đăng nhập"
                autoFocus
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Mật khẩu
              </label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 pr-10 bg-white/10 border border-white/10 rounded-xl text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
                  placeholder="Nhập mật khẩu"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition"
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="px-4 py-2.5 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/25"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <LogIn size={18} />
                  Đăng nhập
                </>
              )}
            </button>
          </form>
        </div>

        {/* Demo accounts */}
        <div className="mt-6 bg-white/[0.05] backdrop-blur-xl border border-white/10 rounded-2xl p-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Demo Accounts — Click để đăng nhập nhanh
          </p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.user}
                onClick={() => quickLogin(acc.user, acc.pw)}
                disabled={loading}
                className="text-left px-3 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-indigo-500/30 transition group disabled:opacity-50"
              >
                <p className="text-sm font-medium text-white group-hover:text-indigo-400 transition">
                  {acc.label}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-tight">
                  {acc.desc}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-slate-600 mt-6">
          BI Dashboard v5.0 • Enterprise Edition
        </p>
      </div>
    </div>
  );
}
