"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { useAuth } from "../store/useAuth";

const ROLE_LABELS: Record<string, string> = {
  executive: "Ban Giám đốc",
  admin: "Admin",
  regional_manager: "Regional Manager",
  store_manager: "Store Manager",
};

const ROLE_COLORS: Record<string, string> = {
  executive: "bg-purple-100 text-purple-700 border-purple-200",
  admin: "bg-red-100 text-red-700 border-red-200",
  regional_manager: "bg-amber-100 text-amber-700 border-amber-200",
  store_manager: "bg-blue-100 text-blue-700 border-blue-200",
};

export default function AuthControl() {
  const router = useRouter();
  const { user, logout, loadFromStorage } = useAuth();

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  if (!user) return null;

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-lg border border-slate-200">
        <User size={14} className="text-slate-500" />
        <span className="text-sm font-medium text-slate-700">{user.display_name || user.username}</span>
        <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full border ${ROLE_COLORS[user.role] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
          {ROLE_LABELS[user.role] || user.role}
        </span>
        {user.region && (
          <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-purple-50 text-purple-600 border border-purple-200">
            {user.region}
          </span>
        )}
      </div>
      <button
        onClick={handleLogout}
        title="Đăng xuất"
        className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
      >
        <LogOut size={16} />
      </button>
    </div>
  );
}
