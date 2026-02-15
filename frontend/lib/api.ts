import type {
  AuthResponse,
  User,
  Campaign,
  Video,
  AnalysisData,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("auth_token")
      : null;

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      body.detail || body.error || `Request failed (${res.status})`
    );
  }

  return res.json();
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      request<AuthResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    register: (email: string, password: string) =>
      request<AuthResponse>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    me: () => request<{ ok: boolean; user: User }>("/api/me"),
  },
  videos: {
    list: () =>
      request<{ ok: boolean; videos: Video[] }>("/api/videos"),
    get: (id: string) =>
      request<{ ok: boolean; video: Campaign }>(`/api/videos/${id}`),
    upload: (file: File) => {
      const formData = new FormData();
      formData.append("video", file);
      return request<{
        ok: boolean;
        videoId: string;
        originalUrl: string;
        processedUrl: string;
        analysisUrl: string;
        variants: { name: string; url: string }[];
      }>("/api/transform", {
        method: "POST",
        body: formData,
      });
    },
  },
  analysis: {
    get: (url: string) => request<AnalysisData>(url),
  },
};
