import type { AnalysisData, Campaign } from "./types";

const MOCK_CAMPAIGNS: Campaign[] = [
  {
    id: "d3m0cafe01a1",
    originalUrl: "",
    analysisUrl: "",
    createdAt: "2026-02-14T19:12:04Z",
    variants: [],
    metadata: {
      speedFactor: 1.08,
      combos: ["hook_caption", "cinematic_grain"],
    },
  },
  {
    id: "d3m0cafe02b2",
    originalUrl: "",
    analysisUrl: "",
    createdAt: "2026-02-13T16:38:27Z",
    variants: [],
    metadata: {
      speedFactor: 1.04,
      combos: ["vertical_focus", "cutdown_fast"],
    },
  },
  {
    id: "d3m0cafe03c3",
    originalUrl: "",
    analysisUrl: "",
    createdAt: "2026-02-12T21:05:11Z",
    variants: [],
    metadata: {
      speedFactor: 1.06,
      combos: ["focus_backdrop", "hook_caption"],
    },
  },
  {
    id: "d3m0cafe04d4",
    originalUrl: "",
    analysisUrl: "",
    createdAt: "2026-02-11T14:19:52Z",
    variants: [],
    metadata: {
      speedFactor: 1.03,
      combos: ["cutdown_fast", "vertical_focus"],
    },
  },
  {
    id: "d3m0cafe05e5",
    originalUrl: "",
    analysisUrl: "",
    createdAt: "2026-02-10T11:44:39Z",
    variants: [],
    metadata: {
      speedFactor: 1.07,
      combos: ["cinematic_grain", "focus_backdrop"],
    },
  },
];

const MOCK_ANALYSIS: Record<string, AnalysisData> = {
  d3m0cafe01a1: {
    captions: [
      { id: "hook", caption: "Cold open: beans hit the grinder." },
      { id: "benefit", caption: "Bright aroma, instant wake-up." },
      { id: "social", caption: "Barista pour with foam art." },
      { id: "cta", caption: "Limited roast drop this week." },
    ],
    events: [
      { t_start: 0, t_end: 3, caption_id: "hook" },
      { t_start: 3, t_end: 7, caption_id: "benefit" },
      { t_start: 7, t_end: 11, caption_id: "social" },
      { t_start: 11, t_end: 15, caption_id: "cta" },
    ],
  },
  d3m0cafe02b2: {
    captions: [
      { id: "hook", caption: "Runner hits a sunrise trail." },
      { id: "product", caption: "Close-up: TrailMix Pro pack." },
      { id: "benefit", caption: "20g protein, zero crash." },
      { id: "cta", caption: "Shop the endurance bundle." },
    ],
    events: [
      { t_start: 0, t_end: 4, caption_id: "hook" },
      { t_start: 4, t_end: 7, caption_id: "product" },
      { t_start: 7, t_end: 12, caption_id: "benefit" },
      { t_start: 12, t_end: 16, caption_id: "cta" },
    ],
  },
  d3m0cafe03c3: {
    captions: [
      { id: "hook", caption: "Before/after skincare glow." },
      { id: "texture", caption: "Serum texture on glass." },
      { id: "routine", caption: "Night routine in three steps." },
      { id: "cta", caption: "Glow kit ships today." },
    ],
    events: [
      { t_start: 0, t_end: 3, caption_id: "hook" },
      { t_start: 3, t_end: 7, caption_id: "texture" },
      { t_start: 7, t_end: 12, caption_id: "routine" },
      { t_start: 12, t_end: 16, caption_id: "cta" },
    ],
  },
  d3m0cafe04d4: {
    captions: [
      { id: "hook", caption: "Desk setup reveal in two cuts." },
      { id: "feature", caption: "Wireless hub snaps into place." },
      { id: "benefit", caption: "Clutter-free charging all day." },
      { id: "cta", caption: "Drop is live tonight." },
    ],
    events: [
      { t_start: 0, t_end: 3, caption_id: "hook" },
      { t_start: 3, t_end: 7, caption_id: "feature" },
      { t_start: 7, t_end: 11, caption_id: "benefit" },
      { t_start: 11, t_end: 15, caption_id: "cta" },
    ],
  },
  d3m0cafe05e5: {
    captions: [
      { id: "hook", caption: "Unboxing the travel kit." },
      { id: "benefit", caption: "Leakproof bottles, TSA-ready." },
      { id: "social", caption: "Packed in under 30 seconds." },
      { id: "cta", caption: "Preorders close Friday." },
    ],
    events: [
      { t_start: 0, t_end: 4, caption_id: "hook" },
      { t_start: 4, t_end: 8, caption_id: "benefit" },
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
