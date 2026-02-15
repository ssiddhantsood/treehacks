"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Campaign, AnalysisData, TimelineEvent } from "@/lib/types";
import { getMockAnalysisById, getMockCampaignById } from "@/lib/mock";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function mediaUrl(path: string) {
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
      <div className="flex h-full items-center justify-center">
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
          Loading...
        </span>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-sm text-muted">Campaign not found.</span>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-12">
      <div className="flex items-baseline justify-between">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          {campaign.id.slice(0, 8)}
        </h1>
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
          {campaign.createdAt}
        </span>
      </div>

      <div className="mt-12 grid gap-16 lg:grid-cols-[1fr_280px]">
        <div>
          <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
            Base creative
          </span>
          {campaign.originalUrl ? (
            <div className="mt-4 border border-border bg-foreground/5">
              <video
                ref={videoRef}
                src={mediaUrl(campaign.originalUrl)}
                controls
                className="w-full"
              />
            </div>
          ) : (
            <div className="mt-4 flex h-56 items-center justify-center border border-dashed border-border bg-foreground/5">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Demo asset placeholder
              </span>
            </div>
          )}

          {campaign.variants.length > 0 && (
            <div className="mt-16">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Variants
              </span>
              <div className="mt-6 grid gap-6 sm:grid-cols-2">
                {campaign.variants.map((variant) => (
                  <div key={variant.url}>
                    <div className="border border-border bg-foreground/5">
                      <video
                        src={mediaUrl(variant.url)}
                        controls
                        className="w-full"
                      />
                    </div>
                    <span className="mt-2 block font-mono text-[11px] uppercase tracking-widest text-muted">
                      {variant.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

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
                    <span className="shrink-0 font-mono text-xs">
                      {formatTime(event.t_start)}
                    </span>
                    <span className="text-xs">{event.caption}</span>
                  </button>
                );
              })}
              <div className="border-t border-border" />
            </div>
          )}

          {campaign.metadata && (
            <div className="mt-12">
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                Details
              </span>
              <div className="mt-4 flex flex-col gap-3">
                {campaign.metadata.speedFactor && (
                  <div className="flex items-baseline justify-between border-t border-border pt-3">
                    <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Speed</span>
                    <span className="font-mono text-xs text-foreground">
                      {campaign.metadata.speedFactor}x
                    </span>
                  </div>
                )}
                {campaign.metadata.combos && campaign.metadata.combos.length > 0 && (
                  <div className="flex items-baseline justify-between border-t border-border pt-3">
                    <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Combos</span>
                    <span className="font-mono text-xs text-foreground">
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
