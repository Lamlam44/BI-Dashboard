"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../store/useAuth";
import DashboardLayout from "../components/DashboardLayout";
import ForecastingClient from "./client-page";
import { allowedRoles } from "../lib/routes";

const ALLOWED_ROLES = allowedRoles('/forecasting');

export default function ForecastingPage() {
  const router = useRouter();
  const { user } = useAuth();

  useEffect(() => {
    if (user && !ALLOWED_ROLES.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [user, router]);

  if (!user || !ALLOWED_ROLES.includes(user.role)) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-[60vh] text-slate-500">
          Đang chuyển hướng...
        </div>
      </DashboardLayout>
    );
  }

  return <ForecastingClient />;
}

