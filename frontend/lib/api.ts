import type {
  AuthResponse,
  User,
  Campaign,
  Video,
  AnalysisData,
  EmbeddingsPoint,
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
    upload: (
      file: File,
      profilesFile?: File | null,
      options?: { name?: string; productDesc?: string; goal?: string }
    ) => {
      const formData = new FormData();
      formData.append("video", file);
      if (profilesFile) {
        formData.append("profiles", profilesFile);
      }
      if (options?.name) formData.append("name", options.name);
      if (options?.productDesc) formData.append("product_desc", options.productDesc);
      if (options?.goal) formData.append("goal", options.goal);
      return request<{
        ok: boolean;
        videoId: string;
        name?: string;
        originalUrl: string;
        processedUrl: string;
        analysisUrl: string;
        variants: { name: string; url: string }[];
      }>("/api/transform", {
        method: "POST",
        body: formData,
      });
    },
    generateAds: (id: string, options?: { groupCount?: number; maxEdits?: number }) =>
      request<{
        ok: boolean;
        variants: { name: string; url: string }[];
        metadata: Campaign["metadata"];
        analysisUrl?: string;
      }>(`/api/videos/${id}/generate-ads`, {
        method: "POST",
        body: JSON.stringify(options ?? {}),
      }),
    delete: (id: string) =>
      request<{ ok: boolean }>(`/api/videos/${id}`, {
        method: "DELETE",
      }),
  },
  analysis: {
    get: (url: string) => request<AnalysisData>(url),
  },
  embeddings: {
    get: (id: string) =>
      request<{ ok: boolean; points: EmbeddingsPoint[]; count: number; source?: string }>(
        `/api/videos/${id}/embeddings`
      ),
  },
};
