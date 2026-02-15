"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Video } from "@/lib/types";
import { getMockCampaigns } from "@/lib/mock";

const COMBO_LABELS: Record<string, string> = {
  hook_caption: "Hook Caption",
  cinematic_grain: "Cinematic Grain",
  vertical_focus: "Vertical Focus",
  cutdown_fast: "Fast Cutdown",
  focus_backdrop: "Focus Backdrop",
};

interface Profile {
  age: string;
  gender: string;
  demographic_info: string;
  previous_search_history: string;
}

function parseCSV(text: string): Profile[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];

  const profiles: Profile[] = [];
  // Simple CSV parse that handles quoted fields
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i];
    const fields: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let j = 0; j < row.length; j++) {
      const ch = row[j];
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === "," && !inQuotes) {
        fields.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    fields.push(current.trim());
    if (fields.length >= 4) {
      profiles.push({
        age: fields[0],
        gender: fields[1],
        demographic_info: fields[2],
        previous_search_history: fields[3],
      });
    }
  }
  return profiles;
}

export default function ConsolePage() {
  const router = useRouter();
  const videoInputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);

  // modal state
  const [showModal, setShowModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [campaignName, setCampaignName] = useState("");
  const [productDesc, setProductDesc] = useState("");
  const [goal, setGoal] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [clusterCount, setClusterCount] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const defaultClusters = useMemo(
    () => Math.max(1, Math.round(Math.sqrt(profiles.length))),
    [profiles.length]
  );

  // sync cluster count to default when profiles change
  useEffect(() => {
    setClusterCount(defaultClusters);
  }, [defaultClusters]);

  useEffect(() => {
    api.videos
      .list()
      .then((res) => {
        setVideos([...res.videos, ...getMockCampaigns()]);
      })
      .catch(() => {
        setVideos(getMockCampaigns());
      })
      .finally(() => setLoading(false));
  }, []);

  const openModal = () => {
    setShowModal(true);
    setSelectedFile(null);
    setCampaignName("");
    setProductDesc("");
    setGoal("");
    setProfiles([]);
    setClusterCount(3);
    setSubmitError("");
  };

  const closeModal = () => setShowModal(false);

  const handleVideoSelect = () => {
    const file = videoInputRef.current?.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleCSVSelect = async () => {
    const file = csvInputRef.current?.files?.[0];
    if (!file) return;
    const text = await file.text();
    const parsed = parseCSV(text);
    setProfiles(parsed);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    setSubmitting(true);
    setSubmitError("");

    try {
      const res = await api.videos.upload(selectedFile);
      setSubmitting(false);
      closeModal();
      router.push(`/console/campaigns/${res.videoId}`);
    } catch (err) {
      setSubmitting(false);
      setSubmitError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const timeAgo = (dateStr: string) => {
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHrs < 1) return "Just now";
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays === 1) return "Yesterday";
    return `${diffDays}d ago`;
  };

  const totalVariants = videos.reduce((acc, v) => acc + (v.variants?.length || 0), 0);

  return (
    <div className="mx-auto max-w-7xl px-8 py-12">
      {/* --- new campaign modal --- */}
      {showModal && (
        <div className="fixed inset-0 z-99999 bg-background flex flex-col">
          <div className="animate-modal-in flex flex-col w-screen h-screen">
            {/* modal header */}
            <div className="flex items-center justify-between px-8 py-5 border-b border-border shrink-0">
              <div className="flex items-center gap-6">
                <span className="text-sm font-medium tracking-widest uppercase">ADAPT</span>
                <span className="text-muted text-xs">→</span>
                <span className="font-mono text-[11px] uppercase tracking-widest text-foreground">New campaign</span>
              </div>
              <button
                onClick={closeModal}
                className="text-muted hover:text-foreground transition-colors cursor-pointer"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 4l12 12M16 4L4 16" />
                </svg>
              </button>
            </div>

            {/* modal body */}
            <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
              <div className="flex-1 grid grid-cols-2 min-h-0">
                {/* --- left column: creative + details --- */}
                <div className="border-r border-border px-8 py-8 overflow-y-auto flex flex-col gap-8">
                  {/* video upload */}
                  <div>
                    <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                      Base creative
                    </span>
                    <input
                      ref={videoInputRef}
                      type="file"
                      accept="video/*"
                      onChange={handleVideoSelect}
                      className="hidden"
                    />
                    <div
                      onClick={() => videoInputRef.current?.click()}
                      className={`mt-3 border border-dashed rounded-lg px-6 py-10 text-center cursor-pointer transition-all ${
                        selectedFile ? "border-foreground bg-foreground/5" : "border-border hover:border-foreground/30"
                      }`}
                    >
                      {selectedFile ? (
                        <div className="flex items-center justify-center gap-3">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-foreground">
                            <path d="M20 6L9 17l-5-5" />
                          </svg>
                          <span className="text-sm font-medium">{selectedFile.name}</span>
                          <span className="text-xs text-muted">
                            ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
                          </span>
                        </div>
                      ) : (
                        <p className="text-sm text-muted">
                          Click to select a video · <span className="text-foreground font-medium">MP4, MOV, WebM</span>
                        </p>
                      )}
                    </div>
                  </div>

                  {/* campaign details */}
                  <div className="border-t border-border pt-8">
                    <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                      Campaign details
                    </span>
                    <div className="mt-4 flex flex-col gap-5">
                      <div className="flex flex-col gap-2">
                        <label className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Campaign name
                        </label>
                        <input
                          type="text"
                          value={campaignName}
                          onChange={(e) => setCampaignName(e.target.value)}
                          placeholder="e.g. Nike — Summer 2026"
                          className="w-full border-b border-border bg-transparent px-0 py-2 text-sm text-foreground placeholder:text-muted/50 outline-none transition-colors focus:border-foreground"
                        />
                      </div>
                      <div className="flex flex-col gap-2">
                        <label className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Product description
                        </label>
                        <textarea
                          value={productDesc}
                          onChange={(e) => setProductDesc(e.target.value)}
                          placeholder="Describe the product or brand being advertised..."
                          rows={3}
                          className="w-full border-b border-border bg-transparent px-0 py-2 text-sm text-foreground placeholder:text-muted/50 outline-none transition-colors focus:border-foreground resize-none"
                        />
                      </div>
                      <div className="flex flex-col gap-2">
                        <label className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Campaign goal
                        </label>
                        <input
                          type="text"
                          value={goal}
                          onChange={(e) => setGoal(e.target.value)}
                          placeholder="e.g. Increase brand awareness in new markets"
                          className="w-full border-b border-border bg-transparent px-0 py-2 text-sm text-foreground placeholder:text-muted/50 outline-none transition-colors focus:border-foreground"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* --- right column: profiles + clustering --- */}
                <div className="px-8 py-8 overflow-y-auto flex flex-col gap-8">
                  {/* CSV import */}
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                        Audience profiles
                      </span>
                      <a
                        href="/mock_profiles.csv"
                        download
                        className="font-mono text-[10px] uppercase tracking-widest text-muted hover:text-foreground transition-colors"
                      >
                        Download template ↓
                      </a>
                    </div>
                    <input
                      ref={csvInputRef}
                      type="file"
                      accept=".csv"
                      onChange={handleCSVSelect}
                      className="hidden"
                    />
                    <div
                      onClick={() => csvInputRef.current?.click()}
                      className={`mt-3 border border-dashed rounded-lg px-6 py-8 text-center cursor-pointer transition-all ${
                        profiles.length > 0 ? "border-foreground bg-foreground/5" : "border-border hover:border-foreground/30"
                      }`}
                    >
                      {profiles.length > 0 ? (
                        <div className="flex items-center justify-center gap-3">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-foreground">
                            <path d="M20 6L9 17l-5-5" />
                          </svg>
                          <span className="text-sm font-medium">{profiles.length} profiles imported</span>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setProfiles([]); }}
                            className="text-xs text-muted hover:text-foreground ml-2 cursor-pointer"
                          >
                            Clear
                          </button>
                        </div>
                      ) : (
                        <p className="text-sm text-muted">
                          Import a CSV · <span className="text-foreground font-medium">age, gender, demographic_info, search_history</span>
                        </p>
                      )}
                    </div>
                  </div>

                  {/* cluster count */}
                  {profiles.length > 0 && (
                    <div className="border-t border-border pt-8">
                      <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                        Clusters
                      </span>
                      <p className="mt-1 text-xs text-muted">
                        Group profiles into audience segments. Default is √n ≈ {defaultClusters}.
                      </p>
                      <div className="mt-4 flex items-center gap-4">
                        <input
                          type="range"
                          min={1}
                          max={profiles.length}
                          value={clusterCount}
                          onChange={(e) => setClusterCount(Number(e.target.value))}
                          className="flex-1 accent-foreground"
                        />
                        <span className="font-mono text-sm tabular-nums w-8 text-right">
                          {clusterCount}
                        </span>
                      </div>
                      <div className="mt-1 flex justify-between text-[10px] text-muted font-mono">
                        <span>1</span>
                        <span>{profiles.length}</span>
                      </div>
                    </div>
                  )}

                  {/* profiles table */}
                  {profiles.length > 0 && (
                    <div className="border-t border-border pt-8">
                      <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                        Imported profiles ({profiles.length})
                      </span>
                      <div className="mt-4 border border-border rounded-lg overflow-hidden">
                        {/* table header */}
                        <div className="grid grid-cols-[50px_60px_1fr_1fr] gap-2 px-3 py-2 bg-foreground/[0.03] border-b border-border">
                          <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Age</span>
                          <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Gender</span>
                          <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Demographic</span>
                          <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Search History</span>
                        </div>
                        {/* rows */}
                        <div className="max-h-[280px] overflow-y-auto">
                          {profiles.map((p, i) => (
                            <div
                              key={i}
                              className="grid grid-cols-[50px_60px_1fr_1fr] gap-2 px-3 py-2 border-b border-border last:border-b-0 text-xs"
                            >
                              <span className="tabular-nums">{p.age}</span>
                              <span className="text-muted">{p.gender}</span>
                              <span className="text-muted truncate" title={p.demographic_info}>
                                {p.demographic_info}
                              </span>
                              <span className="text-muted truncate" title={p.previous_search_history}>
                                {p.previous_search_history}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* modal footer */}
              <div className="border-t border-border px-8 py-4 flex items-center justify-between shrink-0">
                {submitError ? (
                  <p className="text-sm text-red-400">{submitError}</p>
                ) : (
                  <span className="text-xs text-muted">
                    {selectedFile ? `${selectedFile.name}` : "No file selected"}
                    {profiles.length > 0 && ` · ${profiles.length} profiles · ${clusterCount} clusters`}
                  </span>
                )}
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="cursor-pointer px-5 py-2.5 text-sm text-muted hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!selectedFile || submitting}
                    className="cursor-pointer px-8 py-2.5 bg-[#1c1c1c] text-white rounded-full text-sm font-medium hover:bg-black transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {submitting ? "Processing..." : "Launch campaign"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- header --- */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Campaigns</h1>
          <p className="mt-2 text-sm text-muted max-w-md">
            Upload a base creative and generate localized variants for every market.
          </p>
        </div>
        <button
          onClick={openModal}
          className="cursor-pointer px-5 py-2.5 bg-[#1c1c1c] text-white rounded-full text-sm font-medium hover:bg-black transition-colors"
        >
          New campaign
        </button>
      </div>

      {/* --- stats --- */}
      <div className="mt-10 grid grid-cols-3 border border-border rounded-lg overflow-hidden">
        {[
          { value: videos.length.toString(), label: "Campaigns" },
          { value: totalVariants.toString(), label: "Variants generated" },
          { value: videos.length > 0 ? timeAgo(videos[0].createdAt) : "—", label: "Last upload" },
        ].map((stat, i) => (
          <div
            key={stat.label}
            className={`py-6 px-6 ${i > 0 ? "border-l border-border" : ""}`}
          >
            <span className="text-2xl font-bold tracking-tight">{stat.value}</span>
            <span className="mt-1 block font-mono text-[10px] uppercase tracking-widest text-muted">
              {stat.label}
            </span>
          </div>
        ))}
      </div>

      {/* --- campaign list --- */}
      <div className="mt-14">
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
          All campaigns
        </span>

        {loading ? (
          <div className="py-24 flex justify-center">
            <div className="w-5 h-5 border-2 border-foreground/20 border-t-foreground rounded-full animate-spin" />
          </div>
        ) : videos.length === 0 ? (
          <div className="mt-6 py-20 text-center border border-dashed border-border rounded-lg">
            <p className="text-sm text-muted">No campaigns yet. Upload your first creative to get started.</p>
          </div>
        ) : (
          <div className="mt-6 flex flex-col">
            <div className="grid grid-cols-[1fr_140px_140px_100px] gap-4 px-4 py-3 border-b border-border">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Campaign</span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Created</span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Styles</span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted text-right">Variants</span>
            </div>

            {videos.map((video) => {
              const metadata = (video as unknown as { metadata?: { speedFactor?: number; combos?: string[] } }).metadata;
              const combos = metadata?.combos || [];

              return (
                <Link
                  key={video.id}
                  href={`/console/campaigns/${video.id}`}
                  className="group grid grid-cols-[1fr_140px_140px_100px] gap-4 items-center px-4 py-4 border-b border-border transition-colors hover:bg-foreground/[0.02]"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-md bg-foreground/4 border border-border flex items-center justify-center shrink-0 overflow-hidden">
                      {video.originalUrl ? (
                        <video
                          src={video.originalUrl}
                          className="w-full h-full object-cover"
                          muted
                        />
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-muted/50">
                          <rect x="2" y="4" width="20" height="16" rx="2" />
                          <path d="M10 9l5 3-5 3V9z" />
                        </svg>
                      )}
                    </div>
                    <span className="text-sm font-medium group-hover:text-foreground transition-colors truncate">
                      {video.name || `Campaign ${video.id.slice(0, 8)}`}
                    </span>
                  </div>

                  <span className="text-xs text-muted tabular-nums">
                    {formatDate(video.createdAt)}
                  </span>

                  <div className="flex flex-wrap gap-1">
                    {combos.slice(0, 2).map((combo) => (
                      <span
                        key={combo}
                        className="inline-block px-2 py-0.5 text-[10px] text-muted bg-foreground/4 rounded-full truncate max-w-[120px]"
                      >
                        {COMBO_LABELS[combo] || combo}
                      </span>
                    ))}
                    {combos.length === 0 && (
                      <span className="text-[10px] text-muted/50">—</span>
                    )}
                  </div>

                  <div className="text-right">
                    {video.variants && video.variants.length > 0 ? (
                      <span className="text-xs text-foreground font-medium tabular-nums">
                        {video.variants.length}
                      </span>
                    ) : (
                      <span className="text-xs text-muted/50">0</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
