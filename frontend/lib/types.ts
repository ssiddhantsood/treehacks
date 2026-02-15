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
  variantsCount?: number;
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
    groupCount?: number;
    generatedAt?: string;
    groupVariants?: {
      groupId: number;
      label?: string;
      summary?: string;
      research?: {
        ok?: boolean;
        audience?: string;
        insights?: string;
        citations?: string[];
        model?: string;
        error?: string;
        transformations?: string[];
      };
      context?: {
        region?: string;
        country?: string;
        timezone?: string;
        timeOfDay?: string;
        localHour?: number;
        englishSpeaking?: boolean;
        isUrban?: boolean;
        avgAge?: number;
        ageBucket?: string;
        topGenders?: string[];
        interests?: string[];
      };
      planner?: {
        ok?: boolean;
        error?: string;
        model?: string;
        raw?: string;
      };
      variantName?: string;
      variantUrl?: string;
      changes?: {
        tool?: string;
        args?: Record<string, unknown>;
        summary?: string;
        reason?: string;
        apply?: boolean;
        applied?: boolean;
        forced?: boolean;
        source?: string;
        error?: string;
        outputPath?: string;
      }[];
    }[];
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

export interface EmbeddingsPoint {
  x: number;
  y: number;
  z: number;
  groupId: number;
  index: number;
  summary?: string;
}

export interface EmbeddingGroupSummary {
  groupId: number;
  label?: string;
  summary?: string;
  traits?: string[];
  examples?: string[];
  memberCount?: number;
  source?: string;
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
