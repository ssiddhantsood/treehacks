export interface User {
  id: number;
  email: string;
}

export interface VideoVariant {
  name: string;
  url: string;
}

export interface Video {
  id: string;
  name?: string;
  originalUrl: string;
  analysisUrl?: string;
  createdAt: string;
  variants?: VideoVariant[];
}

export interface Campaign {
  id: string;
  name?: string;
  originalUrl: string;
  analysisUrl?: string;
  createdAt: string;
  variants: VideoVariant[];
  metadata?: {
    speedFactor?: number;
    combos?: string[];
  };
}

export interface TimelineEvent {
  t_start: number;
  t_end: number;
  caption_id: string;
  caption?: string;
}

export interface AnalysisData {
  events: TimelineEvent[];
  captions: { id: string; caption: string }[];
}

export interface AuthResponse {
  ok: boolean;
  token: string;
  user: User;
}

export interface ApiError {
  detail?: string;
  error?: string;
}
