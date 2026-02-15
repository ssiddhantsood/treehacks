"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Campaign, AnalysisData, TimelineEvent } from "@/lib/types";
import { getMockAnalysisById, getMockCampaignById } from "@/lib/mock";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function mediaUrl(path: string) {
  if (path.startsWith("/ads/")) return path;
  return `${API_BASE}${path}`;
}

function formatTime(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

type GroupVariant = NonNullable<Campaign["metadata"]>["groupVariants"] extends (infer T)[] | undefined ? T : never;

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(true);

  // generate-ads state
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [groupCount, setGroupCount] = useState(3);
  const [expandedGroup, setExpandedGroup] = useState<number | null>(null);

  useEffect(() => {
    if (!params.id) return;

    api.videos
      .get(params.id)
      .then(async (res) => {
        setCampaign(res.video);
        if (res.video.analysisUrl) {
          try {
            const analysisData = await api.analysis.get(res.video.analysisUrl);
            setAnalysis(analysisData);
          } catch {
          }
        }
      })
      .catch(() => {
        const mockCampaign = getMockCampaignById(params.id);
        if (mockCampaign) {
          setCampaign(mockCampaign);
          const mockAnalysis = getMockAnalysisById(params.id);
          if (mockAnalysis) {
            setAnalysis(mockAnalysis);
          }
        }
      })
      .finally(() => setLoading(false));
  }, [params.id]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeUpdate = () => setCurrentTime(video.currentTime || 0);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, [campaign?.originalUrl]);

  const timelineEvents = useMemo(() => {
    if (!analysis?.events || !analysis?.captions) return [];
    const captions = new Map(
      analysis.captions.map((item) => [item.id, item])
    );
    return analysis.events.map((event) => ({
      ...event,
      caption: captions.get(event.caption_id)?.caption || "No description",
    }));
  }, [analysis]);

  const groupVariants: GroupVariant[] = useMemo(() => {
    return campaign?.metadata?.groupVariants ?? [];
  }, [campaign?.metadata?.groupVariants]);

  const hasGeneratedAds = groupVariants.length > 0;

  const handleGenerateAds = async () => {
    if (!params.id) return;
    setGenerating(true);
    setGenError("");

    try {
      const res = await api.videos.generateAds(params.id, { groupCount });
      setCampaign((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          variants: [...(prev.variants || []), ...(res.variants || [])],
          metadata: res.metadata ?? prev.metadata,
          analysisUrl: res.analysisUrl ?? prev.analysisUrl,
        };
      });
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="w-5 h-5 border-2 border-foreground/20 border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <span className="text-sm text-muted">Campaign not found.</span>
      </div>
    );
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-8 py-12">
      {/* --- breadcrumb --- */}
      <div className="flex items-center gap-2 mb-10">
        <Link
          href="/console"
          className="font-mono text-[11px] uppercase tracking-widest text-muted hover:text-foreground transition-colors"
        >
          Campaigns
        </Link>
        <span className="text-muted text-xs">→</span>
        <span className="font-mono text-[11px] uppercase tracking-widest text-foreground">
          {campaign.name || campaign.id.slice(0, 8)}
        </span>
      </div>

      {/* --- header --- */}
      <div className="flex items-end justify-between border-b border-border pb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {campaign.name || `Campaign ${campaign.id.slice(0, 8)}`}
          </h1>
          <span className="mt-2 block font-mono text-[10px] uppercase tracking-widest text-muted">
            Created {formatDate(campaign.createdAt)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {campaign.variants.length > 0 && (
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
              {campaign.variants.length} variants
            </span>
          )}
        </div>
      </div>

      <div className="mt-12 grid gap-16 lg:grid-cols-[1fr_300px]">
        {/* --- left column --- */}
        <div>
          {/* --- base creative --- */}
          <div>
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
              Base creative
            </span>
            {campaign.originalUrl ? (
              <div className="mt-4 border border-border rounded-lg overflow-hidden bg-foreground/2">
                <video
                  ref={videoRef}
                  src={mediaUrl(campaign.originalUrl)}
                  controls
                  className="w-full"
                />
              </div>
            ) : (
              <div className="mt-4 flex aspect-video items-center justify-center border border-dashed border-border rounded-lg bg-foreground/2">
                <div className="text-center">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-muted/30 mx-auto mb-3">
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <path d="M10 9l5 3-5 3V9z" />
                  </svg>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                    Demo asset
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* --- generate ads panel --- */}
          <div className="mt-16 border-t border-border pt-10">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Audience variants
              </span>
              {hasGeneratedAds && (
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                  Generated {campaign.metadata?.generatedAt ? formatDate(campaign.metadata.generatedAt) : ""}
                </span>
              )}
            </div>

            {!hasGeneratedAds && (
              <div className="mt-6 border border-dashed border-border rounded-lg p-8">
                <p className="text-sm text-muted max-w-md">
                  Generate localized ad variants for different audience segments. Profiles will be clustered and each group
                  gets market research, a transformation plan, and a unique video edit.
                </p>
                <div className="mt-6 flex items-end gap-6">
                  <div className="flex flex-col gap-2">
                    <label className="font-mono text-[10px] uppercase tracking-widest text-muted">
                      Number of groups
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={1}
                        max={10}
                        value={groupCount}
                        onChange={(e) => setGroupCount(Number(e.target.value))}
                        className="w-32 accent-foreground"
                      />
                      <span className="font-mono text-sm tabular-nums w-6 text-right">
                        {groupCount}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={handleGenerateAds}
                    disabled={generating}
                    className="cursor-pointer px-6 py-2.5 bg-[#1c1c1c] text-white rounded-full text-sm font-medium hover:bg-black transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {generating ? (
                      <span className="flex items-center gap-2">
                        <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Generating...
                      </span>
                    ) : (
                      "Generate variants"
                    )}
                  </button>
                </div>
                {genError && (
                  <p className="mt-4 text-sm text-red-400">{genError}</p>
                )}
              </div>
            )}

            {/* --- generated group variants --- */}
            {hasGeneratedAds && (
              <div className="mt-6 flex flex-col gap-4">
                {groupVariants.map((group) => {
                  const isExpanded = expandedGroup === group.groupId;
                  return (
                    <div
                      key={group.groupId}
                      className="border border-border rounded-lg overflow-hidden"
                    >
                      {/* group header */}
                      <button
                        type="button"
                        onClick={() => setExpandedGroup(isExpanded ? null : group.groupId)}
                        className="cursor-pointer w-full flex items-center justify-between px-6 py-5 hover:bg-foreground/[0.02] transition-colors"
                      >
                        <div className="flex items-center gap-4">
                          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-foreground/5 border border-border font-mono text-xs font-medium">
                            {group.groupId}
                          </span>
                          <div className="text-left">
                            <span className="text-sm font-medium">
                              {group.label || `Group ${group.groupId}`}
                            </span>
                            {group.summary && (
                              <span className="block mt-0.5 text-xs text-muted max-w-lg truncate">
                                {group.summary}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {group.context?.region && (
                            <span className="inline-block px-2 py-0.5 text-[10px] text-muted bg-foreground/4 rounded-full">
                              {group.context.region}
                            </span>
                          )}
                          {group.context?.ageBucket && (
                            <span className="inline-block px-2 py-0.5 text-[10px] text-muted bg-foreground/4 rounded-full">
                              {group.context.ageBucket}
                            </span>
                          )}
                          <svg
                            width="16"
                            height="16"
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                            className={`text-muted transition-transform ${isExpanded ? "rotate-180" : ""}`}
                          >
                            <path d="M4 6l4 4 4-4" />
                          </svg>
                        </div>
                      </button>

                      {/* group expanded content */}
                      {isExpanded && (
                        <div className="border-t border-border">
                          <div className="grid gap-0 lg:grid-cols-2">
                            {/* left: video + changes */}
                            <div className="p-6 border-r border-border">
                              {group.variantUrl && (
                                <div className="border border-border rounded-lg overflow-hidden bg-foreground/2">
                                  <video
                                    src={mediaUrl(group.variantUrl)}
                                    controls
                                    className="w-full"
                                  />
                                </div>
                              )}
                              {/* changes / decisions */}
                              {group.changes && group.changes.length > 0 && (
                                <div className="mt-6">
                                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                                    Applied transforms
                                  </span>
                                  <div className="mt-3 flex flex-col gap-0">
                                    {group.changes
                                      .filter((c) => c.apply || c.applied)
                                      .map((change, ci) => (
                                        <div
                                          key={ci}
                                          className="flex items-start gap-3 border-t border-border py-3"
                                        >
                                          <div className="shrink-0 mt-0.5">
                                            {change.applied ? (
                                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-400">
                                                <path d="M20 6L9 17l-5-5" />
                                              </svg>
                                            ) : change.error ? (
                                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-400">
                                                <path d="M18 6L6 18M6 6l12 12" />
                                              </svg>
                                            ) : (
                                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted/40">
                                                <circle cx="12" cy="12" r="10" />
                                              </svg>
                                            )}
                                          </div>
                                          <div className="min-w-0">
                                            <span className="font-mono text-[11px] text-foreground">
                                              {change.tool}
                                            </span>
                                            {change.summary && (
                                              <span className="block mt-0.5 text-xs text-muted">
                                                {change.summary}
                                              </span>
                                            )}
                                            {change.reason && (
                                              <span className="block mt-0.5 text-[11px] text-muted/60 italic">
                                                {change.reason}
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    <div className="border-t border-border" />
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* right: research + context */}
                            <div className="p-6 flex flex-col gap-6">
                              {/* context card */}
                              {group.context && (
                                <div>
                                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                                    Audience context
                                  </span>
                                  <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                                    {group.context.region && (
                                      <ContextRow label="Region" value={group.context.region} />
                                    )}
                                    {group.context.country && (
                                      <ContextRow label="Country" value={group.context.country} />
                                    )}
                                    {group.context.timeOfDay && (
                                      <ContextRow label="Time of day" value={group.context.timeOfDay} />
                                    )}
                                    {group.context.ageBucket && (
                                      <ContextRow label="Age bracket" value={group.context.ageBucket} />
                                    )}
                                    {group.context.avgAge != null && (
                                      <ContextRow label="Avg age" value={String(group.context.avgAge)} />
                                    )}
                                    {group.context.topGenders && group.context.topGenders.length > 0 && (
                                      <ContextRow label="Top genders" value={group.context.topGenders.join(", ")} />
                                    )}
                                    {group.context.isUrban != null && (
                                      <ContextRow label="Urban" value={group.context.isUrban ? "Yes" : "No"} />
                                    )}
                                    {group.context.englishSpeaking != null && (
                                      <ContextRow label="English" value={group.context.englishSpeaking ? "Yes" : "No"} />
                                    )}
                                  </div>
                                  {group.context.interests && group.context.interests.length > 0 && (
                                    <div className="mt-3">
                                      <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                                        Interests
                                      </span>
                                      <div className="mt-1.5 flex flex-wrap gap-1">
                                        {group.context.interests.map((interest, ii) => (
                                          <span
                                            key={ii}
                                            className="inline-block px-2 py-0.5 text-[10px] text-muted bg-foreground/4 rounded-full"
                                          >
                                            {interest}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* research insights */}
                              {group.research?.ok && group.research.insights && (
                                <div>
                                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                                    Market research
                                  </span>
                                  <p className="mt-2 text-xs text-muted leading-relaxed whitespace-pre-wrap">
                                    {group.research.insights}
                                  </p>
                                  {group.research.citations && group.research.citations.length > 0 && (
                                    <div className="mt-3 flex flex-col gap-1">
                                      {group.research.citations.map((cite, ci) => (
                                        <a
                                          key={ci}
                                          href={cite}
                                          target="_blank"
                                          rel="noopener"
                                          className="text-[10px] text-muted/60 hover:text-foreground transition-colors truncate block"
                                        >
                                          {cite}
                                        </a>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* planner status */}
                              {group.planner && (
                                <div>
                                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                                    Planner
                                  </span>
                                  <div className="mt-2 flex items-center gap-2">
                                    {group.planner.ok ? (
                                      <span className="inline-flex items-center gap-1.5 text-[11px] text-green-400">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                          <path d="M20 6L9 17l-5-5" />
                                        </svg>
                                        Constraints satisfied
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-400">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                          <path d="M12 9v4M12 17h.01" />
                                          <circle cx="12" cy="12" r="10" />
                                        </svg>
                                        {group.planner.error || "Partial result"}
                                      </span>
                                    )}
                                    {group.planner.model && (
                                      <span className="text-[10px] text-muted/50 ml-auto">
                                        {group.planner.model}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* re-generate button */}
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-xs text-muted">
                    {groupVariants.length} audience segment{groupVariants.length !== 1 ? "s" : ""}
                  </span>
                  <button
                    onClick={handleGenerateAds}
                    disabled={generating}
                    className="cursor-pointer text-xs text-muted hover:text-foreground transition-colors disabled:opacity-40 flex items-center gap-2"
                  >
                    {generating && (
                      <span className="w-3 h-3 border-2 border-muted/30 border-t-foreground rounded-full animate-spin" />
                    )}
                    Regenerate
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* --- right column --- */}
        <div>
          {/* --- interactive timeline --- */}
          <div>
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
              Timeline
            </span>

            {/* visual timeline bar */}
            {timelineEvents.length > 0 && analysis && (
              <div className="mt-4 mb-2">
                <div className="relative w-full h-2 bg-foreground/5 rounded-full overflow-hidden">
                  {(() => {
                    const duration = timelineEvents[timelineEvents.length - 1]?.t_end || 1;
                    return timelineEvents.map((event: TimelineEvent & { caption: string }, i: number) => {
                      const left = (event.t_start / duration) * 100;
                      const width = ((event.t_end - event.t_start) / duration) * 100;
                      const active = currentTime >= event.t_start && currentTime < event.t_end;
                      return (
                        <button
                          key={`${event.t_start}-${event.caption_id}`}
                          type="button"
                          onClick={() => {
                            if (videoRef.current) {
                              videoRef.current.currentTime = event.t_start;
                              videoRef.current.play();
                            }
                          }}
                          className="absolute top-0 h-full transition-colors cursor-pointer"
                          style={{
                            left: `${left}%`,
                            width: `${width}%`,
                            backgroundColor: active ? "var(--foreground)" : `rgba(var(--foreground-rgb, 0,0,0), ${0.08 + (i % 3) * 0.06})`,
                          }}
                          title={event.caption}
                        />
                      );
                    });
                  })()}
                  {/* playhead */}
                  {(() => {
                    const duration = timelineEvents[timelineEvents.length - 1]?.t_end || 1;
                    const position = (currentTime / duration) * 100;
                    return (
                      <div
                        className="absolute top-0 w-0.5 h-full bg-foreground pointer-events-none"
                        style={{ left: `${Math.min(position, 100)}%` }}
                      />
                    );
                  })()}
                </div>
                <div className="mt-1 flex justify-between text-[9px] text-muted font-mono tabular-nums">
                  <span>{formatTime(0)}</span>
                  <span>{formatTime(timelineEvents[timelineEvents.length - 1]?.t_end || 0)}</span>
                </div>
              </div>
            )}

            {timelineEvents.length === 0 ? (
              <p className="mt-4 text-sm text-muted">
                No timeline available.
              </p>
            ) : (
              <div className="mt-2 flex max-h-[32rem] flex-col gap-0 overflow-y-auto">
                {timelineEvents.map((event: TimelineEvent & { caption: string }) => {
                  const active =
                    currentTime >= event.t_start && currentTime < event.t_end;
                  const duration = event.t_end - event.t_start;
                  return (
                    <button
                      key={`${event.t_start}-${event.caption_id}`}
                      type="button"
                      onClick={() => {
                        if (videoRef.current) {
                          videoRef.current.currentTime = event.t_start;
                          videoRef.current.play();
                        }
                      }}
                      className={`flex items-baseline gap-3 border-t border-border px-0 py-3 text-left transition-colors cursor-pointer ${
                        active
                          ? "text-foreground"
                          : "text-muted hover:text-foreground"
                      }`}
                    >
                      <span className="shrink-0 font-mono text-[11px] tabular-nums">
                        {formatTime(event.t_start)}
                      </span>
                      <span className="text-xs leading-relaxed flex-1">{event.caption}</span>
                      <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted/50">
                        {duration.toFixed(1)}s
                      </span>
                    </button>
                  );
                })}
                <div className="border-t border-border" />
              </div>
            )}
          </div>

          {/* --- details --- */}
          {campaign.metadata && (
            <div className="mt-12">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Details
              </span>
              <div className="mt-4 flex flex-col gap-0">
                {campaign.metadata.speedFactor && (
                  <div className="flex items-baseline justify-between border-t border-border py-3">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Speed</span>
                    <span className="font-mono text-xs text-foreground">
                      {campaign.metadata.speedFactor}×
                    </span>
                  </div>
                )}
                {campaign.metadata.combos && campaign.metadata.combos.length > 0 && (
                  <div className="flex items-baseline justify-between border-t border-border py-3">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Combos</span>
                    <span className="font-mono text-xs text-foreground text-right">
                      {campaign.metadata.combos.join(", ")}
                    </span>
                  </div>
                )}
                {campaign.metadata.groupCount != null && (
                  <div className="flex items-baseline justify-between border-t border-border py-3">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Groups</span>
                    <span className="font-mono text-xs text-foreground">
                      {campaign.metadata.groupCount}
                    </span>
                  </div>
                )}
                <div className="border-t border-border" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 py-1.5">
      <span className="font-mono text-[9px] uppercase tracking-widest text-muted/60">{label}</span>
      <span className="text-xs text-foreground">{value}</span>
    </div>
  );
}
