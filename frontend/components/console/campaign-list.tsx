"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Video } from "@/lib/types";
import { getMockCampaigns } from "@/lib/mock";

export function CampaignList() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.videos
      .list()
      .then((res) => {
        const padded = [...res.videos, ...getMockCampaigns()];
        setVideos(padded);
      })
      .catch(() => {
        setVideos(getMockCampaigns());
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="py-16 text-center font-mono text-[11px] uppercase tracking-widest text-muted">
        Loading...
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div className="border-t border-border py-16 text-center">
        <p className="text-sm text-muted">No campaigns yet. Upload your first ad above.</p>
      </div>
    );
  }

  return (
    <div>
      {videos.map((video) => (
        <Link key={video.id} href={`/console/campaigns/${video.id}`} className="block">
          <div className="grid grid-cols-[auto_1fr_auto] items-baseline gap-8 border-t border-border py-5 transition-colors hover:border-muted">
            <span className="font-mono text-xs text-muted">{video.id.slice(0, 8)}</span>
            <span className="text-sm text-foreground">
              Campaign {video.id.slice(0, 6)}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
              {video.createdAt}
            </span>
          </div>
        </Link>
      ))}
      <div className="border-t border-border" />
    </div>
  );
}
