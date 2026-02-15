import type { AnalysisData, Campaign } from "./types";

const MOCK_CAMPAIGNS: Campaign[] = [
  {
    id: "doritos-sb-2026",
    name: "Doritos — Super Bowl LX",
    originalUrl: "/ads/doritos_sb.webm",
    analysisUrl: "doritos-sb-2026",
    createdAt: "2026-02-14T19:12:04Z",
    variants: [
      { name: "Latin America — Spanish VO", url: "/ads/doritos_sb.webm" },
      { name: "Japan — Tokyo Edit", url: "/ads/doritos_sb.webm" },
      { name: "Germany — Berlin Cut", url: "/ads/doritos_sb.webm" },
    ],
    metadata: {
      speedFactor: 1.08,
      combos: ["hook_caption", "cinematic_grain"],
    },
  },
  {
    id: "nike-sb-2026",
    name: "Nike — \"Never Done\"",
    originalUrl: "/ads/nike_sb.webm",
    analysisUrl: "nike-sb-2026",
    createdAt: "2026-02-13T16:38:27Z",
    variants: [
      { name: "UK — London Localisation", url: "/ads/nike_sb.webm" },
      { name: "France — Paris Edit", url: "/ads/nike_sb.webm" },
    ],
    metadata: {
      speedFactor: 1.04,
      combos: ["vertical_focus", "cutdown_fast"],
    },
  },
  {
    id: "pepsi-sb-2026",
    name: "Pepsi — Halftime Hype",
    originalUrl: "/ads/pepsi_sb.webm",
    analysisUrl: "pepsi-sb-2026",
    createdAt: "2026-02-12T21:05:11Z",
    variants: [
      { name: "Brazil — São Paulo Cut", url: "/ads/pepsi_sb.webm" },
      { name: "India — Mumbai Edit", url: "/ads/pepsi_sb.webm" },
      { name: "Middle East — Dubai Edit", url: "/ads/pepsi_sb.webm" },
      { name: "Japan — Tokyo Cut", url: "/ads/pepsi_sb.webm" },
    ],
    metadata: {
      speedFactor: 1.06,
      combos: ["focus_backdrop", "hook_caption"],
    },
  },
  {
    id: "openai-sb-2026",
    name: "OpenAI — \"Intelligence for Everyone\"",
    originalUrl: "/ads/openai_sb.webm",
    analysisUrl: "openai-sb-2026",
    createdAt: "2026-02-11T14:19:52Z",
    variants: [
      { name: "Korea — Seoul Edit", url: "/ads/openai_sb.webm" },
    ],
    metadata: {
      speedFactor: 1.03,
      combos: ["cutdown_fast", "vertical_focus"],
    },
  },
  {
    id: "tacobell-sb-2026",
    name: "Taco Bell — Live Más",
    originalUrl: "/ads/taco_bell_sb.webm",
    analysisUrl: "tacobell-sb-2026",
    createdAt: "2026-02-10T11:44:39Z",
    variants: [
      { name: "Mexico — CDMX Cut", url: "/ads/taco_bell_sb.webm" },
      { name: "Spain — Madrid Edit", url: "/ads/taco_bell_sb.webm" },
    ],
    metadata: {
      speedFactor: 1.07,
      combos: ["cinematic_grain", "focus_backdrop"],
    },
  },
];

const MOCK_ANALYSIS: Record<string, AnalysisData> = {
  "doritos-sb-2026": {
    captions: [
      { id: "hook", caption: "Crowd roar. Triangle chip snaps in slow motion." },
      { id: "action", caption: "Fan leaps off couch — Dorito mid-air." },
      { id: "comedic", caption: "Dog steals the bag, chaos erupts." },
      { id: "cta", caption: "\"For The Bold\" title card. Stadium cheers." },
    ],
    events: [
      { t_start: 0, t_end: 4, caption_id: "hook" },
      { t_start: 4, t_end: 9, caption_id: "action" },
      { t_start: 9, t_end: 14, caption_id: "comedic" },
      { t_start: 14, t_end: 18, caption_id: "cta" },
    ],
  },
  "nike-sb-2026": {
    captions: [
      { id: "hook", caption: "Athlete trains alone, pre-dawn city streets." },
      { id: "montage", caption: "Quick cuts of sprinting, lifting, pushing limits." },
      { id: "climax", caption: "Finish line moment — arms raised." },
      { id: "cta", caption: "Swoosh fade-in. \"Just Do It.\"" },
    ],
    events: [
      { t_start: 0, t_end: 5, caption_id: "hook" },
      { t_start: 5, t_end: 10, caption_id: "montage" },
      { t_start: 10, t_end: 15, caption_id: "climax" },
      { t_start: 15, t_end: 19, caption_id: "cta" },
    ],
  },
  "pepsi-sb-2026": {
    captions: [
      { id: "hook", caption: "Stadium lights up. Can cracks open." },
      { id: "energy", caption: "Dancers hit the floor, halftime vibes." },
      { id: "celeb", caption: "Celebrity cameo — crowd goes wild." },
      { id: "cta", caption: "\"That's What I Like\" tagline, Pepsi globe spins." },
    ],
    events: [
      { t_start: 0, t_end: 4, caption_id: "hook" },
      { t_start: 4, t_end: 8, caption_id: "energy" },
      { t_start: 8, t_end: 13, caption_id: "celeb" },
      { t_start: 13, t_end: 17, caption_id: "cta" },
    ],
  },
  "openai-sb-2026": {
    captions: [
      { id: "hook", caption: "Child asks a question. AI answers warmly." },
      { id: "demo", caption: "Split-screen: coding, writing, creating, learning." },
      { id: "impact", caption: "Doctor uses AI to diagnose faster." },
      { id: "cta", caption: "\"Intelligence for Everyone\" — openai.com." },
    ],
    events: [
      { t_start: 0, t_end: 5, caption_id: "hook" },
      { t_start: 5, t_end: 10, caption_id: "demo" },
      { t_start: 10, t_end: 15, caption_id: "impact" },
      { t_start: 15, t_end: 20, caption_id: "cta" },
    ],
  },
  "tacobell-sb-2026": {
    captions: [
      { id: "hook", caption: "Late night drive-thru glow. Bass drops." },
      { id: "food", caption: "Crunchwrap close-up, cheese pull." },
      { id: "social", caption: "Friends piling into the car, laughing." },
      { id: "cta", caption: "\"Live Más\" on screen. Bell rings." },
    ],
    events: [
      { t_start: 0, t_end: 4, caption_id: "hook" },
      { t_start: 4, t_end: 8, caption_id: "food" },
      { t_start: 8, t_end: 12, caption_id: "social" },
      { t_start: 12, t_end: 16, caption_id: "cta" },
    ],
  },
};

export function getMockCampaigns(): Campaign[] {
  return MOCK_CAMPAIGNS;
}

export function getMockCampaignById(id: string): Campaign | null {
  return MOCK_CAMPAIGNS.find((campaign) => campaign.id === id) ?? null;
}

export function getMockAnalysisById(id: string): AnalysisData | null {
  return MOCK_ANALYSIS[id] ?? null;
}
