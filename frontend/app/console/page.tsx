"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Video } from "@/lib/types";
import { getMockCampaigns } from "@/lib/mock";
import { TriangleAlert, X } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function mediaUrl(path: string) {
  if (path.startsWith("/ads/")) return path;
  return `${API_BASE}${path}`;
}

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
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i];
    const fields: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let j = 0; j < row.length; j++) {
      const ch = row[j];
      if (ch === '"') inQuotes = !inQuotes;
      else if (ch === "," && !inQuotes) { fields.push(current.trim()); current = ""; }
      else current += ch;
    }
    fields.push(current.trim());
    if (fields.length >= 4) profiles.push({ age: fields[0], gender: fields[1], demographic_info: fields[2], previous_search_history: fields[3] });
  }
  return profiles;
}

export default function ConsolePage() {
  const router = useRouter();
  const videoInputRef = useRef<HTMLInputElement>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [modalStep, setModalStep] = useState<1 | 2 | 3>(1);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [campaignName, setCampaignName] = useState("");
  const [productDesc, setProductDesc] = useState("");
  const [goal, setGoal] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfilesFile, setSelectedProfilesFile] = useState<File | null>(null);
  const [clusterCount, setClusterCount] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [draggingVideo, setDraggingVideo] = useState(false);
  const [draggingCSV, setDraggingCSV] = useState(false);
  const recentSectionRef = useRef<HTMLDivElement>(null);
  const rightPanelRef = useRef<HTMLDivElement>(null);
  const [gridViewportHeight, setGridViewportHeight] = useState(0);
  const gridTopPadding = 32;
  // Grid layout state
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);
  const videoRefs = useRef<{ [key: string]: HTMLVideoElement }>({});
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const pendingPreviews = useRef<Record<string, string>>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");

  const handleMouseEnter = (id: string, index: number) => {
    setHoveredCard(index);
    const video = videoRefs.current[id];
    if (video) {
        video.currentTime = 0;
        video.play().catch(() => {});
    }
  };

  const handleMouseLeave = (id: string) => {
    setHoveredCard(null);
    const video = videoRefs.current[id];
    if (video) {
        video.pause();
        video.currentTime = 0;
    }
  };

  const defaultClusters = useMemo(() => Math.max(1, Math.round(Math.sqrt(profiles.length))), [profiles.length]);

  useEffect(() => { setClusterCount(defaultClusters); }, [defaultClusters]);

  useEffect(() => {
    api.videos.list()
      .then((res) => setVideos([...res.videos, ...getMockCampaigns()]))
      .catch(() => setVideos(getMockCampaigns()))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const section = recentSectionRef.current;
    const rightPanel = rightPanelRef.current;
    if (!section || !rightPanel) return;

    const updateHeight = () => {
      const sectionRect = section.getBoundingClientRect();
      const rightRect = rightPanel.getBoundingClientRect();
      const height = Math.max(0, Math.round(sectionRect.bottom - rightRect.top - gridTopPadding));
      setGridViewportHeight(height);
    };

    updateHeight();

    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateHeight);
    observer.observe(section);
    observer.observe(rightPanel);
    return () => observer.disconnect();
  }, []);

  const openModal = () => {
    setShowModal(true);
    setModalStep(1);
    setSelectedFile(null);
    setCampaignName("");
    setProductDesc("");
    setGoal("");
    setProfiles([]);
    setSelectedProfilesFile(null);
    setClusterCount(3);
    setSubmitError("");
  };

  const closeModal = () => setShowModal(false);

  const handleVideoSelect = (e?: React.ChangeEvent<HTMLInputElement> | File) => {
    if (e instanceof File) { setSelectedFile(e); return; }
    const file = e?.target.files?.[0] || videoInputRef.current?.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleCSVSelect = async (e?: React.ChangeEvent<HTMLInputElement> | File) => {
    let file: File | undefined;
    if (e instanceof File) file = e;
    else file = e?.target.files?.[0] || csvInputRef.current?.files?.[0];
    if (!file) return;
    setSelectedProfilesFile(file);
    setProfiles(parseCSV(await file.text()));
  };

  const handleDropVideo = (e: React.DragEvent) => {
    e.preventDefault();
    setDraggingVideo(false);
    const file = e.dataTransfer.files?.[0];
    if (file?.type.startsWith("video/")) handleVideoSelect(file);
  };

  const handleDropCSV = (e: React.DragEvent) => {
    e.preventDefault();
    setDraggingCSV(false);
    const file = e.dataTransfer.files?.[0];
    if (file && (file.type === "text/csv" || file.name.endsWith(".csv"))) handleCSVSelect(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const pendingId = `pending-${Date.now()}`;
      const previewUrl = URL.createObjectURL(selectedFile);
      pendingPreviews.current[pendingId] = previewUrl;
      setPendingIds((prev) => new Set(prev).add(pendingId));
      setVideos((prev) => [
        {
          id: pendingId,
          name: campaignName || "Processing campaign",
          originalUrl: previewUrl,
          createdAt: new Date().toISOString(),
          variants: [],
          variantsCount: 0,
        },
        ...prev,
      ]);
      closeModal();

      const res = await api.videos.upload(selectedFile, selectedProfilesFile, {
        name: campaignName || undefined,
        productDesc: productDesc || undefined,
        goal: goal || undefined,
      });
      setVideos((prev) => [
        {
          id: res.videoId,
          name: res.name || campaignName || undefined,
          originalUrl: res.originalUrl,
          analysisUrl: res.analysisUrl,
          createdAt: new Date().toISOString(),
          variants: res.variants || [],
        },
        ...prev.filter((video) => video.id !== pendingId),
      ]);
      const pendingUrl = pendingPreviews.current[pendingId];
      if (pendingUrl) {
        URL.revokeObjectURL(pendingUrl);
        delete pendingPreviews.current[pendingId];
      }
      setPendingIds((prev) => {
        const next = new Set(prev);
        next.delete(pendingId);
        return next;
      });
      setSubmitting(false);
    } catch (err) {
      setSubmitting(false);
      setSubmitError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  const handleDeleteCampaign = (id: string) => {
    setDeleteError("");
    setPendingDeleteId(id);
    setShowDeleteConfirm(true);
  };

  const confirmDeleteCampaign = async () => {
    if (!pendingDeleteId) return;
    setDeleteError("");
    try {
      await api.videos.delete(pendingDeleteId);
      setVideos((prev) => prev.filter((video) => video.id !== pendingDeleteId));
      setShowDeleteConfirm(false);
      setPendingDeleteId(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const totalVariants = videos.reduce((acc, v) => acc + (v.variants?.length ?? v.variantsCount ?? 0), 0);

  return (
    <div className="h-full w-full overflow-hidden bg-background">
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-[9999] bg-black/30 flex items-center justify-center">
          <div className="w-full max-w-sm rounded-2xl bg-background p-7 shadow-2xl ring-1 ring-border/60">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Confirm deletion</span>
                <h3 className="mt-3 text-lg font-semibold">Delete campaign?</h3>
                <p className="mt-2 text-sm text-muted">
                  This removes the campaign, variants, and analysis. This cannot be undone.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setPendingDeleteId(null);
                }}
                className="text-muted hover:text-foreground transition-colors cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>
            <div className="mt-5 flex items-center gap-3 rounded-xl border border-amber-200/40 bg-amber-500/5 px-3 py-2">
              <div className="w-7 h-7 rounded-full bg-amber-500/10 border border-amber-400/40 flex items-center justify-center">
                <TriangleAlert size={14} className="text-amber-500" />
              </div>
              <span className="text-xs text-muted">If you want to keep variants, export them before deleting.</span>
            </div>
            {deleteError && <p className="mt-4 text-xs text-red-400">{deleteError}</p>}
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setPendingDeleteId(null);
                }}
                className="px-4 py-2 text-xs text-muted hover:text-foreground transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDeleteCampaign}
                className="px-4 py-2 text-xs font-medium bg-foreground text-background rounded-full hover:bg-foreground/90 cursor-pointer"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ═══════════════════════════════════════════════════════════════════════
          MODAL - Full Redesign with Steps
      ═══════════════════════════════════════════════════════════════════════ */}
      {showModal && (
        <div className="fixed inset-0 z-[99999] bg-background">
          <div className="animate-modal-in h-full flex flex-col">
            {/* Modal Nav */}
            <div className="shrink-0 flex items-center justify-between px-8 h-16 border-b border-border">
              <div className="flex items-center gap-8">
                <span className="text-sm font-medium tracking-widest uppercase">ADAPT</span>
                <div className="flex items-center gap-1">
                  {[1, 2, 3].map((step) => (
                    <button
                      key={step}
                      onClick={() => step < modalStep && setModalStep(step as 1 | 2 | 3)}
                      className={`flex items-center gap-2 px-3 py-1.5 text-xs font-mono transition-all cursor-pointer ${
                        modalStep === step
                          ? "text-foreground"
                          : modalStep > step
                            ? "text-foreground/50"
                            : "text-muted/40"
                      }`}
                    >
                      <span className="text-[10px]">
                        {modalStep > step ? "✓" : `0${step}`}
                      </span>
                      <span className="hidden sm:inline uppercase tracking-widest">
                        {step === 1 ? "Creative" : step === 2 ? "Details" : "Audience"}
                      </span>
                    </button>
                  ))}
                  {/* Dividers between steps */}
                </div>
              </div>
              <button
                onClick={closeModal}
                className="w-8 h-8 rounded-full hover:bg-foreground/5 flex items-center justify-center text-muted hover:text-foreground transition-colors cursor-pointer"
              >
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 4l12 12M16 4L4 16" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-hidden">
              {/* Step 1: Upload Creative */}
              {modalStep === 1 && (
                <div className="h-full flex">
                  {/* Left - Upload Zone */}
                  <div className="flex-1 flex items-center justify-center p-12">
                    <input ref={videoInputRef} type="file" accept="video/*" onChange={handleVideoSelect} className="hidden" />
                    
                    {selectedFile ? (
                      <div className="w-full max-w-2xl">
                        <div className="aspect-video bg-black rounded-2xl overflow-hidden border border-border relative group">
                          <video
                            src={URL.createObjectURL(selectedFile)}
                            className="w-full h-full object-contain"
                            controls
                            autoPlay
                            muted
                          />
                          <button
                            onClick={() => setSelectedFile(null)}
                            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                          >
                            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path d="M4 4l12 12M16 4L4 16" />
                            </svg>
                          </button>
                        </div>
                        <div className="mt-6 flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{selectedFile.name}</p>
                            <p className="text-xs text-muted mt-1">{(selectedFile.size / (1024 * 1024)).toFixed(1)} MB</p>
                          </div>
                          <button
                            onClick={() => videoInputRef.current?.click()}
                            className="px-4 py-2 text-sm text-muted hover:text-foreground transition-colors cursor-pointer"
                          >
                            Change file
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        onClick={() => videoInputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setDraggingVideo(true); }}
                        onDragLeave={() => setDraggingVideo(false)}
                        onDrop={handleDropVideo}
                        className={`w-full max-w-2xl aspect-video rounded-2xl border-2 border-dashed flex flex-col items-center justify-center cursor-pointer transition-all ${
                          draggingVideo
                            ? "border-foreground bg-foreground/5 scale-[1.02]"
                            : "border-border hover:border-foreground/30 hover:bg-foreground/2"
                        }`}
                      >
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className={`mb-6 transition-colors ${draggingVideo ? "text-foreground" : "text-muted/40"}`}>
                          <path d="M12 5v14M5 12h14" />
                        </svg>
                        <p className="text-sm font-medium">Drop your video here</p>
                        <p className="text-xs text-muted mt-2">or click to browse</p>
                        <p className="font-mono text-[10px] text-muted/40 mt-6 uppercase tracking-widest">MP4 · MOV · WebM · up to 500MB</p>
                      </div>
                    )}
                  </div>

                  {/* Right - Info Panel */}
                  <div className="w-80 border-l border-border p-8 flex flex-col">
                    <div>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Step 1 of 3</span>
                      <h2 className="mt-2 text-xl font-bold">Base Creative</h2>
                      <p className="mt-3 text-sm text-muted leading-relaxed">
                        Upload your master video. This will be analyzed and transformed into multiple localized variants.
                      </p>
                    </div>

                    <div className="mt-8 pt-8 border-t border-border">
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Supported formats</span>
                      <div className="mt-3 flex flex-wrap gap-3">
                        {["MP4", "MOV", "WebM", "AVI"].map((f) => (
                          <span key={f} className="font-mono text-[10px] text-muted uppercase tracking-widest">{f}</span>
                        ))}
                      </div>
                    </div>

                    <div className="mt-8 pt-8 border-t border-border">
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">What happens next</span>
                      <ul className="mt-3 space-y-3">
                        {["AI analyzes your video", "Scenes & subjects detected", "Ready for localization"].map((item, i) => (
                          <li key={i} className="flex items-center gap-3 text-xs text-muted">
                            <span className="font-mono text-[9px] text-muted/40">{String(i + 1).padStart(2, "0")}</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="mt-auto pt-8">
                      <button
                        onClick={() => setModalStep(2)}
                        disabled={!selectedFile}
                        className="w-full py-3 bg-foreground text-background rounded-full text-sm font-medium hover:bg-foreground/90 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-all"
                      >
                        Continue
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 2: Campaign Details */}
              {modalStep === 2 && (
                <div className="h-full flex">
                  <div className="flex-1 flex items-center justify-center p-12">
                    <div className="w-full max-w-lg">
                      <div className="space-y-8">
                        <div>
                          <label className="font-mono text-[10px] uppercase tracking-widest text-muted">Campaign name</label>
                          <input
                            type="text"
                            value={campaignName}
                            onChange={(e) => setCampaignName(e.target.value)}
                            placeholder="e.g. Nike — Summer 2026"
                            className="mt-3 w-full px-0 py-4 text-2xl font-semibold bg-transparent border-b-2 border-border focus:border-foreground outline-none transition-colors placeholder:text-muted/30"
                          />
                        </div>

                        <div>
                          <label className="font-mono text-[10px] uppercase tracking-widest text-muted">Product description</label>
                          <textarea
                            value={productDesc}
                            onChange={(e) => setProductDesc(e.target.value)}
                            placeholder="Describe what's being advertised..."
                            rows={4}
                            className="mt-3 w-full px-0 py-3 text-sm bg-transparent border-b border-border focus:border-foreground outline-none transition-colors resize-none placeholder:text-muted/50"
                          />
                        </div>

                        <div>
                          <label className="font-mono text-[10px] uppercase tracking-widest text-muted">Campaign goal</label>
                          <input
                            type="text"
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            placeholder="e.g. Increase brand awareness in new markets"
                            className="mt-3 w-full px-0 py-3 text-sm bg-transparent border-b border-border focus:border-foreground outline-none transition-colors placeholder:text-muted/50"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="w-80 border-l border-border p-8 flex flex-col">
                    <div>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Step 2 of 3</span>
                      <h2 className="mt-2 text-xl font-bold">Campaign Details</h2>
                      <p className="mt-3 text-sm text-muted leading-relaxed">
                        Tell us about your campaign. This helps our AI make better localization decisions.
                      </p>
                    </div>

                    {selectedFile && (
                      <div className="mt-8 pt-8 border-t border-border">
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Selected file</span>
                        <div className="mt-3 aspect-video rounded-lg overflow-hidden border border-border bg-black">
                          <video src={URL.createObjectURL(selectedFile)} className="w-full h-full object-cover" muted />
                        </div>
                        <p className="mt-2 text-xs text-muted truncate">{selectedFile.name}</p>
                      </div>
                    )}

                    <div className="mt-auto pt-8 space-y-3">
                      <button
                        onClick={() => setModalStep(3)}
                        className="w-full py-3 bg-foreground text-background rounded-full text-sm font-medium hover:bg-foreground/90 cursor-pointer transition-all"
                      >
                        Continue
                      </button>
                      <button
                        onClick={() => setModalStep(1)}
                        className="w-full py-3 text-sm text-muted hover:text-foreground cursor-pointer transition-colors"
                      >
                        Back
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 3: Audience */}
              {modalStep === 3 && (
                <div className="h-full flex">
                  <div className="flex-1 p-12 overflow-y-auto">
                    <input ref={csvInputRef} type="file" accept=".csv" onChange={handleCSVSelect} className="hidden" />
                    
                    {profiles.length === 0 ? (
                      <div className="h-full flex items-center justify-center">
                        <div
                          onClick={() => csvInputRef.current?.click()}
                          onDragOver={(e) => { e.preventDefault(); setDraggingCSV(true); }}
                          onDragLeave={() => setDraggingCSV(false)}
                          onDrop={handleDropCSV}
                          className={`w-full max-w-xl aspect-[3/2] rounded-2xl border-2 border-dashed flex flex-col items-center justify-center cursor-pointer transition-all ${
                            draggingCSV
                              ? "border-foreground bg-foreground/5 scale-[1.02]"
                              : "border-border hover:border-foreground/30"
                          }`}
                        >
                          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className={`mb-4 transition-colors ${draggingCSV ? "text-foreground" : "text-muted/40"}`}>
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                            <path d="M14 2v6h6" />
                            <path d="M12 18v-6M9 15h6" />
                          </svg>
                          <p className="text-sm font-medium">Import audience profiles</p>
                          <p className="text-xs text-muted mt-2">CSV with age, gender, demographics</p>
                          <a
                            href="/mock_profiles.csv"
                            download
                            onClick={(e) => e.stopPropagation()}
                            className="mt-6 text-xs text-muted hover:text-foreground underline"
                          >
                            Download template
                          </a>
                        </div>
                      </div>
                    ) : (
                      <div className="max-w-3xl mx-auto">
                        <div className="flex items-center justify-between mb-8">
                          <div className="flex items-center gap-4">
                            <div className="flex items-center justify-center">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-foreground">
                                <path d="M20 6L9 17l-5-5" />
                              </svg>
                            </div>
                            <div>
                              <p className="font-medium">{profiles.length} profiles imported</p>
                              <p className="text-xs text-muted">Ready for clustering</p>
                            </div>
                          </div>
                          <button
                            onClick={() => {
                              setProfiles([]);
                              setSelectedProfilesFile(null);
                            }}
                            className="text-xs text-muted hover:text-foreground cursor-pointer"
                          >
                            Remove
                          </button>
                        </div>

                        <div className="p-6 border border-border rounded-2xl mb-8">
                          <div className="flex items-center justify-between mb-4">
                            <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                              Audience segments
                            </span>
                            <span className="text-2xl font-bold">{clusterCount}</span>
                          </div>
                  <input
                    type="range"
                    min={1}
                    max={Math.max(1, profiles.length)}
                    value={clusterCount}
                    onChange={(e) => setClusterCount(Number(e.target.value))}
                    className="w-full h-2 appearance-none bg-foreground/10 rounded-full cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-foreground"
                  />
                  <div className="flex justify-between mt-2 text-xs text-muted font-mono">
                    <span>1</span>
                    <span>{Math.max(1, profiles.length)}</span>
                  </div>
                        </div>

                        <div className="border border-border rounded-2xl overflow-hidden">
                          <div className="grid grid-cols-[60px_80px_1fr_1fr] gap-4 px-4 py-3 bg-foreground/2 border-b border-border">
                            <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Age</span>
                            <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Gender</span>
                            <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Demographic</span>
                            <span className="font-mono text-[9px] uppercase tracking-widest text-muted">Interests</span>
                          </div>
                          <div className="max-h-64 overflow-y-auto">
                            {profiles.slice(0, 20).map((p, i) => (
                              <div key={i} className="grid grid-cols-[60px_80px_1fr_1fr] gap-4 px-4 py-3 border-b border-border last:border-b-0 text-sm">
                                <span className="tabular-nums">{p.age}</span>
                                <span className="text-muted">{p.gender}</span>
                                <span className="text-muted truncate">{p.demographic_info}</span>
                                <span className="text-muted truncate">{p.previous_search_history}</span>
                              </div>
                            ))}
                          </div>
                          {profiles.length > 20 && (
                            <div className="px-4 py-3 text-xs text-muted text-center bg-foreground/2">
                              + {profiles.length - 20} more profiles
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="w-80 border-l border-border p-8 flex flex-col">
                    <div>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Step 3 of 3</span>
                      <h2 className="mt-2 text-xl font-bold">Target Audience</h2>
                      <p className="mt-3 text-sm text-muted leading-relaxed">
                        Import your audience data. We&apos;ll cluster them into segments and generate variants for each.
                      </p>
                    </div>

                    <div className="mt-8 pt-8 border-t border-border">
                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Summary</span>
                      <div className="mt-4 flex flex-col divide-y divide-border">
                        <div className="flex items-center justify-between py-3">
                          <span className="text-sm text-muted">Creative</span>
                          <span className="text-sm font-medium truncate max-w-[140px]">{selectedFile?.name || "—"}</span>
                        </div>
                        <div className="flex items-center justify-between py-3">
                          <span className="text-sm text-muted">Campaign</span>
                          <span className="text-sm font-medium truncate max-w-[140px]">{campaignName || "Untitled"}</span>
                        </div>
                        <div className="flex items-center justify-between py-3">
                          <span className="text-sm text-muted">Profiles</span>
                          <span className="text-sm font-medium">{profiles.length || 0}</span>
                        </div>
                        <div className="flex items-center justify-between py-3">
                          <span className="text-sm text-muted">Segments</span>
                          <span className="text-sm font-medium">{clusterCount}</span>
                        </div>
                      </div>
                    </div>

                    {submitError && (
                      <p className="mt-4 text-sm text-red-500">{submitError}</p>
                    )}

                    <div className="mt-auto pt-8 space-y-3">
                      <button
                        onClick={handleSubmit}
                        disabled={submitting}
                        className="w-full py-3 bg-foreground text-background rounded-full text-sm font-medium hover:bg-foreground/90 disabled:opacity-50 cursor-pointer transition-all flex items-center justify-center gap-2"
                      >
                        {submitting ? (
                          <>
                            <span className="w-4 h-4 border-2 border-background/30 border-t-background rounded-full animate-spin" />
                            Processing...
                          </>
                        ) : (
                          "Launch Campaign"
                        )}
                      </button>
                      <button
                        onClick={() => setModalStep(2)}
                        disabled={submitting}
                        className="w-full py-3 text-sm text-muted hover:text-foreground cursor-pointer transition-colors disabled:opacity-50"
                      >
                        Back
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════
          MAIN PAGE
      ═══════════════════════════════════════════════════════════════════════ */}
      <div className="relative h-full w-full">
        {/* Left Panel - Info */}
          <div className="absolute left-0 top-0 bottom-0 w-[400px] p-8 flex flex-col z-10">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Campaigns</h1>
            <p className="mt-3 text-sm text-muted leading-relaxed max-w-xs">
              Your localized ad campaigns. Each card represents a master creative with its variants.
            </p>
          </div>

          {/* Stats */}
          <div className="mt-10 grid grid-cols-2 gap-4">
            {[
              { value: videos.length, label: "Campaigns" },
              { value: totalVariants, label: "Variants" },
              { value: "12", label: "Markets" },
              { value: "+41%", label: "Avg. lift" },
            ].map((stat) => (
              <div key={stat.label} className="py-4 px-4 border border-border rounded-xl">
                <span className="text-2xl font-bold">{stat.value}</span>
                <span className="block font-mono text-[9px] uppercase tracking-widest text-muted mt-1">{stat.label}</span>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="mt-10">
            <button
              onClick={openModal}
              className="w-full py-3.5 bg-foreground text-background rounded-full text-sm font-medium hover:bg-foreground/90 cursor-pointer transition-all"
            >
              New campaign
            </button>
          </div>

          {/* Recent List */}
            <div ref={recentSectionRef} className="mt-10 flex-1 min-h-0 flex flex-col relative">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Recent</span>
            <div className="mt-4 space-y-0 overflow-y-auto flex-1 -mr-4 pr-4">
              {videos.slice(0, 6).map((video, i) => {
                const isPending = pendingIds.has(video.id);
                return (
                  <Link
                    key={video.id}
                    href={`/console/campaigns/${video.id}`}
                    onClick={(e) => {
                      if (isPending) {
                        e.preventDefault();
                        e.stopPropagation();
                      }
                    }}
                    onMouseEnter={() => setHoveredCard(i)}
                    onMouseLeave={() => setHoveredCard(null)}
                    className={`flex items-center gap-3 py-3 border-b border-border transition-colors ${
                      hoveredCard === i ? "bg-foreground/2" : ""
                    } ${isPending ? "opacity-70" : ""}`}
                  >
                    <span className="font-mono text-[10px] text-muted w-5">{String(i + 1).padStart(2, "0")}</span>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium block truncate">{video.name || `Campaign ${video.id.slice(0, 8)}`}</span>
                      <span className="text-[10px] text-muted">{video.variants?.length ?? video.variantsCount ?? 0} variants</span>
                    </div>
                  {isPending ? (
                    <span className="flex items-center gap-2 text-[10px] text-muted">
                      <span className="w-2.5 h-2.5 border-2 border-muted/40 border-t-foreground rounded-full animate-spin" />
                      Processing
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted">{formatDate(video.createdAt)}</span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleDeleteCampaign(video.id);
                    }}
                    className="ml-2 font-mono text-[9px] uppercase tracking-widest text-muted/70 hover:text-foreground transition-colors cursor-pointer"
                  >
                    Delete
                  </button>
                  </Link>
                );
              })}
            </div>
            <div className="absolute bottom-0 left-0 right-0 h-12 bg-linear-to-t from-background to-transparent pointer-events-none" />
          </div>
        </div>

        {/* Right Panel - Visual Stack */}
        {/* Right Panel - Grid */}
        <div ref={rightPanelRef} className="absolute right-0 top-0 bottom-0 left-[400px] bg-background">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-foreground/20 border-t-foreground rounded-full animate-spin" />
            </div>
          ) : videos.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="w-20 h-20 mx-auto rounded-full bg-foreground/3 border border-dashed border-border flex items-center justify-center mb-6">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-muted/50">
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <path d="M10 9l5 3-5 3V9z" />
                  </svg>
                </div>
                <p className="text-muted">No campaigns yet</p>
                <button
                  onClick={openModal}
                  className="mt-4 px-6 py-2.5 bg-foreground text-background rounded-full text-sm font-medium cursor-pointer"
                >
                  Create your first
                </button>
              </div>
            </div>
          ) : (
            <div
              className="w-full overflow-y-auto px-8"
              style={{ height: gridViewportHeight ? `${gridViewportHeight}px` : "100%", marginTop: gridTopPadding }}
            >
               <div className="grid grid-cols-2 gap-2">
                {videos.map((video, i) => {
                  const isHovered = hoveredCard === i;

                  return (
                    <Link
                      key={video.id}
                      href={`/console/campaigns/${video.id}`}
                      onMouseEnter={() => handleMouseEnter(video.id, i)}
                      onMouseLeave={() => handleMouseLeave(video.id)}
                      className={`relative w-full aspect-16/10 transition-all duration-300 ease-out group ${isHovered ? 'z-10 scale-[1.02]' : 'z-0 scale-100'}`}
                    >
                      <div
                        style={{
                          width: "100%",
                          height: "100%",
                          padding: "0",
                          display: "flex",
                          flexDirection: "column",
                          position: "relative",
                        }}
                      >
                        <div
                          className="relative w-full flex-1 overflow-hidden rounded-lg bg-neutral-900 isolate"
                        >
                            {video.originalUrl ? (
                                <video
                                  ref={(el) => { if (el) videoRefs.current[video.id] = el; }}
                                 src={mediaUrl(video.originalUrl)}
                                 className="absolute inset-0 w-full h-full object-cover"
                                 loop
                                 muted
                                 playsInline
                               />
                            ) : (
                              <div className="absolute inset-0 flex items-center justify-center">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-foreground/20">
                                  <rect x="2" y="4" width="20" height="16" rx="2" />
                                  <path d="M10 9l5 3-5 3V9z" />
                                </svg>
                              </div>
                            )}
                            {/* Default overlay — visible when NOT hovered */}
                            <div className="absolute inset-0 bg-black/50 flex flex-col justify-between p-4 transition-opacity duration-300 group-hover:opacity-0">
                              <div />
                              <div className="flex flex-col items-center text-center gap-1">
                                 <span className="font-mono text-xs text-white font-medium tracking-wide drop-shadow-md">
                                   {video.name || "Untitled"}
                                 </span>
                                 <span className="font-mono text-[10px] text-white/60 uppercase tracking-widest drop-shadow-md">
                                   {video.variants?.length ?? video.variantsCount ?? 0} variants
                                 </span>
                              </div>
                              <div className="flex justify-between items-end">
                                <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                                  {formatDate(video.createdAt)}
                                </span>
                                <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                                  {String(i + 1).padStart(2, "0")}
                                </span>
                              </div>
                            </div>


                            {/* Hover overlay — fades in on hover */}
                            <div className="absolute inset-x-0 bottom-0 h-24 bg-linear-to-t from-black/70 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                            <div className="absolute inset-x-0 bottom-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-between items-end pointer-events-none">
                              <span className="font-mono text-[10px] text-white uppercase tracking-widest drop-shadow-sm">
                                {video.name || "Untitled"}
                              </span>
                              <span className="font-mono text-[10px] text-white/80 uppercase tracking-widest drop-shadow-sm">
                                {video.variants?.length ?? video.variantsCount ?? 0} VARIANTS
                              </span>
                            </div>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
