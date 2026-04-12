import axios from "axios";

// [CLOUD - COMMENTED OUT] Render deployment URL
// export const API_BASE_URL =
//   typeof window !== "undefined" && window.location.hostname === "localhost"
//     ? "http://localhost:8000"
//     : "https://bi-dashboard-3nmr.onrender.com";

// [LOCAL] Always point to local backend
export const API_BASE_URL = "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("bi_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

/** Global 401 handler: clear stale token and redirect to login. */
function handleUnauthorized() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("bi_token");
  localStorage.removeItem("bi_user");
  window.location.href = "/login";
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      handleUnauthorized();
    }
    return Promise.reject(error);
  }
);

export default api;

/** Helper for raw fetch calls that also injects auth token. */
export function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("bi_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Authenticated fetch wrapper.
 * Redirects to /login automatically on 401 (expired / invalid token).
 */
export async function authenticatedFetch(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, { ...init, headers: { ...authHeaders(), ...(init?.headers || {}) } });
  if (res.status === 401) {
    handleUnauthorized();
    // Return a never-resolving promise so callers don't process a 401 body
    return new Promise(() => {});
  }
  return res;
}
