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

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(true);

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
        {campaign.variants.length > 0 && (
          <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
            {campaign.variants.length} variants
          </span>
        )}
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

          {/* --- variants --- */}
          {campaign.variants.length > 0 && (
            <div className="mt-16 border-t border-border pt-10">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Variants
              </span>
              <div className="mt-6 grid gap-6 sm:grid-cols-2">
                {campaign.variants.map((variant) => (
                  <div key={variant.name}>
                    <div className="border border-border rounded-lg overflow-hidden bg-foreground/2">
                      <video
                        src={mediaUrl(variant.url)}
                        controls
                        className="w-full"
                      />
                    </div>
                    <span className="mt-3 block font-mono text-[10px] uppercase tracking-widest text-muted">
                      {variant.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* --- right column --- */}
        <div>
          {/* --- highlights --- */}
          <div>
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
              Highlights
            </span>
            {timelineEvents.length === 0 ? (
              <p className="mt-4 text-sm text-muted">
                No highlights available.
              </p>
            ) : (
              <div className="mt-4 flex max-h-[32rem] flex-col gap-0 overflow-y-auto">
                {timelineEvents.map((event: TimelineEvent & { caption: string }) => {
                  const active =
                    currentTime >= event.t_start && currentTime < event.t_end;
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
                      <span className="text-xs leading-relaxed">{event.caption}</span>
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
                <div className="border-t border-border" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
