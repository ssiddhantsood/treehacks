"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Campaign, AnalysisData, TimelineEvent, EmbeddingsPoint, EmbeddingGroupSummary } from "@/lib/types";
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

const MAP_SIZE = 520;
const CUBE_SIZE = MAP_SIZE * 0.72;
const CAMERA_DISTANCE = MAP_SIZE * 1.6;
const ZOOM_MIN = 0.65;
const ZOOM_MAX = 2.4;
const DEFAULT_ROTATION = { x: -0.35, y: 0.65 };

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const parseProfileSummary = (summary?: string) => {
  if (!summary) return { age: undefined as number | undefined, gender: undefined as string | undefined, demo: "" };
  const parts = summary.split(", ");
  const age = Number(parts[0]);
  const gender = parts[1]?.trim();
  const demo = parts.slice(2).join(", ").trim();
  return {
    age: Number.isFinite(age) ? age : undefined,
    gender: gender || undefined,
    demo,
  };
};

const buildFactsFromContext = (context?: GroupVariant["context"]) => {
  if (!context) return "";
  const parts: string[] = [];
  if (context.avgAge) parts.push(`avg age ${Math.round(context.avgAge)}`);
  if (context.ageBucket) parts.push(context.ageBucket);
  if (context.topGenders?.length) parts.push(`top genders: ${context.topGenders.slice(0, 2).join(", ")}`);
  if (context.interests?.length) parts.push(`interests: ${context.interests.slice(0, 3).join(", ")}`);
  return parts.join(" · ");
};

type BasePoint = EmbeddingsPoint & {
  x3: number;
  y3: number;
  z3: number;
};

type MapPoint = BasePoint & {
  sx: number;
  sy: number;
  depth: number;
  scale: number;
};

const buildFactsFromPoints = (points: EmbeddingsPoint[]) => {
  if (!points.length) return "";
  let ageTotal = 0;
  let ageCount = 0;
  const genderCounts = new Map<string, number>();
  const demoSamples: string[] = [];
  const seenDemo = new Set<string>();

  for (const point of points) {
    const info = parseProfileSummary(point.summary);
    if (info.age !== undefined) {
      ageTotal += info.age;
      ageCount += 1;
    }
    if (info.gender) {
      genderCounts.set(info.gender, (genderCounts.get(info.gender) || 0) + 1);
    }
    if (info.demo && demoSamples.length < 2 && !seenDemo.has(info.demo)) {
      seenDemo.add(info.demo);
      demoSamples.push(info.demo);
    }
  }

  const parts: string[] = [];
  parts.push(points.length === 1 ? "1 profile" : `${points.length} profiles`);
  if (ageCount > 0) parts.push(`avg age ${Math.round(ageTotal / ageCount)}`);
  if (genderCounts.size > 0) {
    const topGenders = Array.from(genderCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
      .map(([gender]) => gender);
    if (topGenders.length) parts.push(`top genders: ${topGenders.join(", ")}`);
  }
  if (demoSamples.length) parts.push(`demo: ${demoSamples.join("; ")}`);
  return parts.join(" · ");
};

function EmbeddingsMap({
  points,
  groupVariants,
  groupSummaries,
  groupColor,
  source,
  expanded = false,
  onExpand,
  onClose,
}: {
  points: EmbeddingsPoint[];
  groupVariants: GroupVariant[];
  groupSummaries?: EmbeddingGroupSummary[];
  groupColor: (groupId: number) => string;
  source?: string | null;
  expanded?: boolean;
  onExpand?: () => void;
  onClose?: () => void;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState({ ...DEFAULT_ROTATION });
  const [isDragging, setIsDragging] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState<MapPoint | null>(null);
  const [hoveredGroup, setHoveredGroup] = useState<number | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null);
  const dragStart = useRef({ x: 0, y: 0 });
  const offsetStart = useRef({ x: 0, y: 0 });
  const rotationStart = useRef({ x: 0, y: 0 });
  const dragMode = useRef<"rotate" | "pan">("rotate");
  const dragged = useRef(false);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        requestAnimationFrame(() => {
          setViewportSize({ width: entry.contentRect.width, height: entry.contentRect.height });
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const basePoints: BasePoint[] = useMemo(() => {
    return points.map((point) => {
      const zValue = Number.isFinite(point.z) ? point.z : 0.5;
      return {
        ...point,
        x3: (point.x - 0.5) * CUBE_SIZE,
        y3: (0.5 - point.y) * CUBE_SIZE,
        z3: (zValue - 0.5) * CUBE_SIZE,
      };
    });
  }, [points]);

  const groupPoints = useMemo(() => {
    const map = new Map<number, BasePoint[]>();
    basePoints.forEach((point) => {
      const existing = map.get(point.groupId) || [];
      existing.push(point);
      map.set(point.groupId, existing);
    });
    return map;
  }, [basePoints]);

  const groupList = useMemo(() => {
    const groupIds = new Set<number>();
    groupVariants.forEach((group) => groupIds.add(group.groupId));
    basePoints.forEach((point) => groupIds.add(point.groupId));

    return Array.from(groupIds)
      .sort((a, b) => a - b)
      .map((groupId) => {
        const variant = groupVariants.find((group) => group.groupId === groupId);
        const groupPts = groupPoints.get(groupId) || [];
        const summaryEntry = groupSummaries?.find((group) => group.groupId === groupId);
        const label = summaryEntry?.label || variant?.label || `Group ${groupId}`;
        const summaryLine = summaryEntry?.summary?.trim() || "";
        const traitsLine = summaryEntry?.traits?.length ? summaryEntry.traits.join(" · ") : "";
        const examplesLine = summaryEntry?.examples?.length ? summaryEntry.examples.join(" | ") : "";
        const fallbackFacts = buildFactsFromContext(variant?.context) || buildFactsFromPoints(groupPts) || variant?.summary || "";
        const facts = summaryLine || fallbackFacts;
        const details = summaryLine ? traitsLine : "";
        const examplesLabel = examplesLine.includes("|") ? "Examples" : "Example";
        return {
          groupId,
          label,
          facts,
          details,
          examples: examplesLine,
          examplesLabel,
          count: summaryEntry?.memberCount ?? groupPts.length,
        };
      });
  }, [groupVariants, groupPoints, basePoints, groupSummaries]);

  const groupMap = useMemo(() => {
    const map = new Map<number, (typeof groupList)[number]>();
    groupList.forEach((group) => map.set(group.groupId, group));
    return map;
  }, [groupList]);

  const centroidBases = useMemo(() => {
    const map = new Map<number, { x: number; y: number; z: number; count: number }>();
    basePoints.forEach((point) => {
      const existing = map.get(point.groupId) || { x: 0, y: 0, z: 0, count: 0 };
      existing.x += point.x3;
      existing.y += point.y3;
      existing.z += point.z3;
      existing.count += 1;
      map.set(point.groupId, existing);
    });
    return Array.from(map.entries()).map(([groupId, data]) => ({
      groupId,
      x3: data.count ? data.x / data.count : 0,
      y3: data.count ? data.y / data.count : 0,
      z3: data.count ? data.z / data.count : 0,
    }));
  }, [basePoints]);

  const activeGroupId = selectedGroup ?? hoveredPoint?.groupId ?? hoveredGroup ?? null;
  const activeGroup = activeGroupId !== null ? groupMap.get(activeGroupId) : null;

  const projection = useMemo(() => {
    return {
      centerX: viewportSize.width / 2 + offset.x,
      centerY: viewportSize.height / 2 + offset.y,
      camera: CAMERA_DISTANCE / zoom,
      cosY: Math.cos(rotation.y),
      sinY: Math.sin(rotation.y),
      cosX: Math.cos(rotation.x),
      sinX: Math.sin(rotation.x),
    };
  }, [viewportSize, offset, rotation, zoom]);

  const projectedPoints: MapPoint[] = useMemo(() => {
    const { centerX, centerY, camera, cosY, sinY, cosX, sinX } = projection;
    const data = basePoints.map((point) => {
      const x1 = point.x3 * cosY + point.z3 * sinY;
      const z1 = -point.x3 * sinY + point.z3 * cosY;
      const y2 = point.y3 * cosX - z1 * sinX;
      const z2 = point.y3 * sinX + z1 * cosX;
      const scale = camera / (camera - z2);
      return {
        ...point,
        sx: centerX + x1 * scale,
        sy: centerY + y2 * scale,
        depth: z2,
        scale,
      };
    });
    data.sort((a, b) => a.depth - b.depth);
    return data;
  }, [basePoints, projection]);

  const centroids = useMemo(() => {
    const { centerX, centerY, camera, cosY, sinY, cosX, sinX } = projection;
    return centroidBases.map((centroid) => {
      const x1 = centroid.x3 * cosY + centroid.z3 * sinY;
      const z1 = -centroid.x3 * sinY + centroid.z3 * cosY;
      const y2 = centroid.y3 * cosX - z1 * sinX;
      const z2 = centroid.y3 * sinX + z1 * cosX;
      const scale = camera / (camera - z2);
      return {
        groupId: centroid.groupId,
        x: centerX + x1 * scale,
        y: centerY + y2 * scale,
        depth: z2,
      };
    });
  }, [centroidBases, projection]);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    dragged.current = false;
    setIsDragging(true);
    dragStart.current = { x: event.clientX, y: event.clientY };
    offsetStart.current = { ...offset };
    rotationStart.current = { ...rotation };
    dragMode.current = event.shiftKey ? "pan" : "rotate";
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    const dx = event.clientX - dragStart.current.x;
    const dy = event.clientY - dragStart.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) dragged.current = true;
    if (dragMode.current === "pan") {
      setOffset({ x: offsetStart.current.x + dx, y: offsetStart.current.y + dy });
    } else {
      setRotation({
        x: clamp(rotationStart.current.x + dy * 0.005, -1.2, 1.2),
        y: rotationStart.current.y + dx * 0.005,
      });
    }
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setIsDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const nextZoom = clamp(zoom * (event.deltaY < 0 ? 1.08 : 0.92), ZOOM_MIN, ZOOM_MAX);
    setZoom(nextZoom);
  };

  const resetView = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    setRotation({ ...DEFAULT_ROTATION });
  };

  const mapHeight = expanded ? "h-full" : "h-[280px]";

  return (
    <div className={expanded ? "flex flex-col h-full" : ""}>
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Embeddings map</span>
          {source && (
            <span className="font-mono text-[9px] uppercase tracking-widest text-muted">
              {source}
            </span>
          )}
          <span className="font-mono text-[9px] uppercase tracking-widest text-muted/70">
            drag to rotate · shift+drag to pan · scroll to zoom
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!expanded && onExpand && (
            <button
              type="button"
              onClick={onExpand}
              className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono text-muted hover:text-foreground border border-border rounded-full transition-colors"
            >
              Open map
            </button>
          )}
          {expanded && onClose && (
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono text-muted hover:text-foreground border border-border rounded-full transition-colors"
            >
              Close
            </button>
          )}
        </div>
      </div>

      <div className={expanded ? "mt-4 grid grid-cols-[minmax(0,1fr)_320px] gap-5 flex-1" : "mt-4 space-y-3"}>
        <div className={`relative ${mapHeight}`}>
          <div
            ref={viewportRef}
            className={`absolute inset-0 rounded-2xl border border-border bg-foreground/3 overflow-hidden touch-none ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
            onWheel={handleWheel}
            onClick={() => {
              if (dragged.current) return;
              setSelectedGroup(null);
            }}
          >
            <div className="absolute inset-0">
              <div
                className="absolute inset-0"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 20% 20%, rgba(255,255,255,0.08), transparent 40%), radial-gradient(circle at 80% 10%, rgba(255,255,255,0.04), transparent 50%)",
                }}
              />
            </div>
            <div className="absolute inset-0">
              <div
                className="absolute inset-0 rounded-2xl border border-border/40"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 50% 50%, rgba(0,0,0,0.12), transparent 55%), radial-gradient(circle at 35% 30%, rgba(0,0,0,0.06), transparent 50%)",
                }}
              />
              {projectedPoints.map((point) => {
                const isActive = !activeGroupId || activeGroupId === point.groupId;
                const baseSize = activeGroupId === point.groupId ? 10 : 8;
                const size = clamp(baseSize * point.scale, 5.5, 16);
                const depthAlpha = clamp((point.scale - 0.6) / 1.4, 0.25, 1);
                return (
                  <button
                    key={`point-${point.index}`}
                    type="button"
                    onMouseEnter={() => setHoveredPoint(point)}
                    onMouseLeave={() => setHoveredPoint(null)}
                    onFocus={() => setHoveredPoint(point)}
                    onBlur={() => setHoveredPoint(null)}
                    onPointerDown={(event) => event.stopPropagation()}
                    className="absolute rounded-full border border-background/60 transition-transform"
                    style={{
                      left: point.sx,
                      top: point.sy,
                      width: size,
                      height: size,
                      opacity: isActive ? depthAlpha : 0.18,
                      backgroundColor: groupColor(point.groupId),
                      transform: "translate(-50%, -50%)",
                    }}
                  />
                );
              })}
              {centroids.map((centroid) => {
                const group = groupMap.get(centroid.groupId);
                const showLabel = expanded || basePoints.length <= 40 || activeGroupId === centroid.groupId;
                if (!showLabel || !group) return null;
                const isActive = !activeGroupId || activeGroupId === centroid.groupId;
                return (
                  <button
                    key={`label-${centroid.groupId}`}
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedGroup((prev) => (prev === centroid.groupId ? null : centroid.groupId));
                    }}
                    onMouseEnter={() => setHoveredGroup(centroid.groupId)}
                    onMouseLeave={() => setHoveredGroup(null)}
                    className="absolute px-2 py-1 rounded-full text-[9px] font-mono uppercase tracking-widest border border-border/70 bg-background/90 shadow-sm"
                    style={{
                      left: centroid.x,
                      top: centroid.y,
                      transform: "translate(-50%, -50%)",
                      color: isActive ? "var(--foreground)" : "rgba(0,0,0,0.5)",
                    }}
                  >
                    {group.label}
                  </button>
                );
              })}
            </div>

            {hoveredPoint && (
              <div
                className="absolute pointer-events-none"
                style={{
                  left: hoveredPoint.sx,
                  top: hoveredPoint.sy,
                  transform: "translate(14px, -14px)",
                }}
              >
                <div className="max-w-[220px] rounded-lg border border-border bg-background/95 shadow-lg px-3 py-2 text-[11px]">
                  <div className="font-mono text-[9px] uppercase tracking-widest text-muted">
                    {groupMap.get(hoveredPoint.groupId)?.label || `Group ${hoveredPoint.groupId}`}
                  </div>
                  {hoveredPoint.summary && (
                    <div className="mt-1 text-foreground leading-snug">{hoveredPoint.summary}</div>
                  )}
                  {groupMap.get(hoveredPoint.groupId)?.facts && (
                    <div className="mt-1 text-muted leading-snug">{groupMap.get(hoveredPoint.groupId)?.facts}</div>
                  )}
                  {groupMap.get(hoveredPoint.groupId)?.examples && (
                    <div className="mt-1 text-muted/80 leading-snug">
                      {(groupMap.get(hoveredPoint.groupId)?.examplesLabel || "Example")}: {groupMap.get(hoveredPoint.groupId)?.examples}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="absolute bottom-3 left-3 flex items-center gap-2">
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setZoom((prev) => clamp(prev * 1.1, ZOOM_MIN, ZOOM_MAX));
                }}
                className="h-8 w-8 rounded-full border border-border bg-background/80 text-xs font-semibold"
              >
                +
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setZoom((prev) => clamp(prev * 0.9, ZOOM_MIN, ZOOM_MAX));
                }}
                className="h-8 w-8 rounded-full border border-border bg-background/80 text-xs font-semibold"
              >
                -
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  resetView();
                }}
                className="px-3 h-8 rounded-full border border-border bg-background/80 text-[10px] font-mono uppercase tracking-widest text-muted"
              >
                Reset
              </button>
            </div>

            {activeGroup && (
              <div className="absolute top-3 left-3 max-w-[60%] rounded-full border border-border bg-background/80 px-3 py-1 text-[10px] font-mono uppercase tracking-widest text-muted">
                {activeGroup.label}{activeGroup.facts ? ` · ${activeGroup.facts}` : ""}
              </div>
            )}
          </div>
        </div>

        <div className={expanded ? "flex flex-col gap-2 overflow-y-auto pr-1" : "grid gap-2"}>
          {groupList.map((group) => {
            const isActive = activeGroupId === group.groupId;
            return (
              <button
                key={`group-${group.groupId}`}
                type="button"
                onMouseEnter={() => setHoveredGroup(group.groupId)}
                onMouseLeave={() => setHoveredGroup(null)}
                onClick={() => setSelectedGroup((prev) => (prev === group.groupId ? null : group.groupId))}
                className={`flex flex-col gap-1 rounded-xl border px-3 py-2 text-left transition-colors ${
                  isActive ? "border-foreground/60 bg-foreground/5" : "border-border/70 hover:border-foreground/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: groupColor(group.groupId) }}
                  />
                  <span className="text-xs font-medium">{group.label}</span>
                  <span className="text-[10px] font-mono text-muted">{group.count} profiles</span>
                </div>
                {group.facts && <div className="text-[11px] text-muted leading-snug">{group.facts}</div>}
                {group.details && <div className="text-[11px] text-muted/80 leading-snug">{group.details}</div>}
                {group.examples && (
                  <div className="text-[10px] text-muted/70 leading-snug">
                    {group.examplesLabel || "Example"}: {group.examples}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const variantRefs = useRef<Record<string, HTMLVideoElement>>({});
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(true);

  // generate-ads state
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [groupCount, setGroupCount] = useState(3);
  const [expandedGroup, setExpandedGroup] = useState<number | null>(null);
  const [hoveredVariant, setHoveredVariant] = useState<string | null>(null);
  const [embeddings, setEmbeddings] = useState<EmbeddingsPoint[]>([]);
  const [embeddingsSource, setEmbeddingsSource] = useState<string | null>(null);
  const [embeddingsError, setEmbeddingsError] = useState("");
  const [embeddingsCount, setEmbeddingsCount] = useState(0);
  const [embeddingGroups, setEmbeddingGroups] = useState<EmbeddingGroupSummary[]>([]);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [mapOpen, setMapOpen] = useState(false);
  const groupCountTouched = useRef(false);

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
    if (!params.id) return;
    setEmbeddingsError("");
    api.embeddings
      .get(params.id)
      .then((res) => {
        setEmbeddings(res.points || []);
        setEmbeddingsSource(res.source || null);
        setEmbeddingGroups(res.groups || []);
        const groupTotal = new Set((res.points || []).map((point) => point.groupId)).size;
        setEmbeddingsCount(groupTotal);
      })
      .catch((err) => {
        setEmbeddings([]);
        setEmbeddingsSource(null);
        setEmbeddingsError(err instanceof Error ? err.message : "Embeddings unavailable");
        setEmbeddingsCount(0);
        setEmbeddingGroups([]);
      });
  }, [params.id]);

  useEffect(() => {
    if (groupCountTouched.current) return;
    setGroupCount(Math.max(1, embeddingsCount || 0));
  }, [embeddingsCount]);

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
  const targetedAdsCount = groupVariants.length;
  const effectiveGroupCount = Math.max(1, embeddingsCount || groupCount);
  const groupCountLocked = embeddingsCount > 0;
  const activeGroup = useMemo(
    () => groupVariants.find((group) => group.groupId === expandedGroup) || null,
    [expandedGroup, groupVariants]
  );

  const displayVariants = useMemo(() => {
    return groupVariants.map((group) => ({
      id: `group-${group.groupId}`,
      title: group.label || `Group ${group.groupId}`,
      subtitle: group.summary || "Audience segment",
      url: group.variantUrl,
    }));
  }, [groupVariants]);

  const groupColor = (groupId: number) => `hsl(${(groupId * 67) % 360} 78% 44%)`;

  const handleVariantEnter = (id: string) => {
    setHoveredVariant(id);
    const video = variantRefs.current[id];
    if (video) {
      video.currentTime = 0;
      video.play().catch(() => {});
    }
  };

  const handleVariantLeave = (id: string) => {
    setHoveredVariant(null);
    const video = variantRefs.current[id];
    if (video) {
      video.pause();
      video.currentTime = 0;
    }
  };

  const handleDeleteCampaign = () => {
    setDeleteError("");
    setShowDeleteConfirm(true);
  };

  const confirmDeleteCampaign = async () => {
    if (!params.id) return;
    setDeleteError("");
    try {
      await api.videos.delete(params.id);
      window.location.href = "/console";
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleGenerateAds = async () => {
    if (!params.id) return;
    setGenerating(true);
    setGenError("");

    try {
      const res = await api.videos.generateAds(params.id, { groupCount: effectiveGroupCount });
      setCampaign((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          variants: res.variants || [],
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
    <div className="h-full w-full overflow-hidden bg-background">
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-[9999] bg-background/80 backdrop-blur-sm flex items-center justify-center">
          <div className="w-full max-w-md border border-border rounded-2xl bg-background p-8 shadow-xl">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Confirm deletion</span>
                <h3 className="mt-3 text-lg font-semibold">Delete campaign?</h3>
                <p className="mt-2 text-sm text-muted">
                  This removes the campaign, ads, analysis, and profiles. This cannot be undone.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="text-muted hover:text-foreground transition-colors cursor-pointer"
              >
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 4l12 12M16 4L4 16" />
                </svg>
              </button>
            </div>
            {deleteError && <p className="mt-4 text-xs text-red-400">{deleteError}</p>}
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
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
      {mapOpen && (
        <div className="fixed inset-0 z-[9998] bg-background/90 backdrop-blur-sm">
          <div className="absolute inset-0 p-6">
            <div className="h-full w-full rounded-3xl border border-border bg-background shadow-2xl p-6">
              <EmbeddingsMap
                points={embeddings}
                groupVariants={groupVariants}
                groupSummaries={embeddingGroups}
                groupColor={groupColor}
                source={embeddingsSource}
                expanded
                onClose={() => setMapOpen(false)}
              />
            </div>
          </div>
        </div>
      )}
      <div className="relative h-full w-full">
        <div className="absolute left-0 top-0 bottom-0 w-[400px] p-8 flex flex-col z-10">
          <Link
            href="/console"
            className="font-mono text-[10px] uppercase tracking-widest text-muted hover:text-foreground transition-colors"
          >
            ← Campaigns
          </Link>

          <div className="mt-6">
            <h1 className="text-2xl font-bold tracking-tight">
              {campaign.name || `Campaign ${campaign.id.slice(0, 8)}`}
            </h1>
            <p className="mt-2 text-xs text-muted">
              Created {formatDate(campaign.createdAt)}
            </p>
          </div>

          <div className="mt-8 grid grid-cols-2 gap-4">
            {[
              { value: targetedAdsCount, label: "Targeted ads" },
              { value: campaign.metadata?.groupCount || groupVariants.length || "—", label: "Groups" },
              { value: analysis ? "Ready" : "Pending", label: "Analysis" },
              { value: campaign.metadata?.generatedAt ? formatDate(campaign.metadata.generatedAt) : "—", label: "Generated" },
            ].map((stat) => (
              <div key={stat.label} className="py-4 px-4 border border-border rounded-xl">
                <span className="text-2xl font-bold tabular-nums">{stat.value}</span>
                <span className="block font-mono text-[9px] uppercase tracking-widest text-muted mt-1">
                  {stat.label}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-8 border-t border-border pt-6">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                Audience ads
              </span>
              {hasGeneratedAds && campaign.metadata?.generatedAt && (
                <span className="font-mono text-[9px] uppercase tracking-widest text-muted">
                  {formatDate(campaign.metadata.generatedAt)}
                </span>
              )}
            </div>
            <p className="mt-3 text-xs text-muted leading-relaxed">
              Cluster profiles and generate tailored edits. Each segment gets research, a plan, and a targeted ad cut.
            </p>
            <div className="mt-5">
              <button
                onClick={handleGenerateAds}
                disabled={generating}
                className="cursor-pointer px-5 py-2.5 bg-foreground text-background rounded-full text-xs font-medium hover:bg-foreground/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {generating ? (
                  <span className="flex items-center gap-2">
                    <span className="w-3.5 h-3.5 border-2 border-background/30 border-t-background rounded-full animate-spin" />
                    Generating...
                  </span>
                ) : (
                  hasGeneratedAds ? "Regenerate" : "Generate"
                )}
              </button>
            </div>
            {genError && <p className="mt-4 text-xs text-red-400">{genError}</p>}
          </div>

          <div className="mt-8 border-t border-border pt-6">
            <button
              type="button"
              onClick={handleDeleteCampaign}
              className="font-mono text-[10px] uppercase tracking-widest text-muted/70 hover:text-red-500 transition-colors"
            >
              Delete campaign
            </button>
          </div>

        </div>

        <div className="absolute right-0 top-0 bottom-0 left-[400px] bg-background overflow-y-auto p-8">
          <div className="max-w-5xl">
            <div>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Base creative</span>
              {campaign.originalUrl ? (
                <div className="mt-4 border border-border rounded-2xl overflow-hidden bg-foreground/2">
                  <video
                    ref={videoRef}
                    src={mediaUrl(campaign.originalUrl)}
                    controls
                    className="w-full"
                  />
                </div>
              ) : (
                <div className="mt-4 flex aspect-video items-center justify-center border border-dashed border-border rounded-2xl bg-foreground/2">
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

            <div className="mt-8">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Timeline</span>
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
                <p className="mt-4 text-sm text-muted">No timeline available.</p>
              ) : (
                <div className="mt-2 flex max-h-[20rem] flex-col gap-0 overflow-y-auto">
                  {timelineEvents.map((event: TimelineEvent & { caption: string }) => {
                    const active = currentTime >= event.t_start && currentTime < event.t_end;
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
                          active ? "text-foreground" : "text-muted hover:text-foreground"
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

            <div className="mt-12">
              {embeddingsError ? (
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Embeddings map</span>
                    {embeddingsSource && (
                      <span className="font-mono text-[9px] uppercase tracking-widest text-muted">
                        {embeddingsSource}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 border border-dashed border-border rounded-2xl p-6 text-xs text-muted">
                    {embeddingsError}
                  </div>
                </div>
              ) : embeddings.length === 0 ? (
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Embeddings map</span>
                    {embeddingsSource && (
                      <span className="font-mono text-[9px] uppercase tracking-widest text-muted">
                        {embeddingsSource}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 border border-dashed border-border rounded-2xl p-6 text-xs text-muted">
                    Upload audience profiles to see the embeddings map.
                  </div>
                </div>
              ) : (
                <div className="mt-4 border border-border rounded-2xl bg-foreground/2 p-4">
                  <EmbeddingsMap
                    points={embeddings}
                    groupVariants={groupVariants}
                    groupSummaries={embeddingGroups}
                    groupColor={groupColor}
                    source={embeddingsSource}
                    onExpand={() => setMapOpen(true)}
                  />
                </div>
              )}
            </div>

            <div className="mt-12">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Targeted ads</span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                  {displayVariants.length} total
                </span>
              </div>
              {displayVariants.length === 0 ? (
                <div className="mt-6 border border-dashed border-border rounded-2xl p-8 text-sm text-muted">
                  No targeted ads yet. Generate segments to get your first cut.
                </div>
              ) : (
                <div className="mt-6 grid grid-cols-2 gap-3">
                  <div
                    className="relative w-full aspect-16/10 rounded-lg overflow-hidden border border-border bg-neutral-900"
                    onMouseEnter={() => handleVariantEnter("base")}
                    onMouseLeave={() => handleVariantLeave("base")}
                  >
                    {campaign.originalUrl ? (
                      <video
                        ref={(el) => { if (el) variantRefs.current.base = el; }}
                        src={mediaUrl(campaign.originalUrl)}
                        className="absolute inset-0 w-full h-full object-cover"
                        loop
                        muted
                        playsInline
                      />
                    ) : null}
                    <div className="absolute inset-0 bg-black/50 flex flex-col justify-between p-4 transition-opacity duration-300">
                      <div />
                      <div className="flex flex-col items-center text-center gap-1">
                        <span className="font-mono text-xs text-white font-medium tracking-wide drop-shadow-md">
                          Base creative
                        </span>
                        <span className="font-mono text-[10px] text-white/60 uppercase tracking-widest drop-shadow-md">
                          Original
                        </span>
                      </div>
                      <div className="flex justify-between items-end">
                        <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                          {formatDate(campaign.createdAt)}
                        </span>
                        <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                          00
                        </span>
                      </div>
                    </div>
                  </div>

                  {displayVariants.map((variant, index) => {
                    const isHovered = hoveredVariant === variant.id;
                    return (
                      <div
                        key={variant.id}
                        onMouseEnter={() => handleVariantEnter(variant.id)}
                        onMouseLeave={() => handleVariantLeave(variant.id)}
                        className={`relative w-full aspect-16/10 rounded-lg overflow-hidden border border-border bg-neutral-900 transition-all duration-300 ease-out ${isHovered ? "z-10 scale-[1.02]" : "z-0"}`}
                      >
                        {variant.url ? (
                          <video
                            ref={(el) => { if (el) variantRefs.current[variant.id] = el; }}
                            src={mediaUrl(variant.url)}
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
                        <div className="absolute inset-0 bg-black/50 flex flex-col justify-between p-4 transition-opacity duration-300">
                          <div />
                          <div className="flex flex-col items-center text-center gap-1">
                            <span className="font-mono text-xs text-white font-medium tracking-wide drop-shadow-md">
                              {variant.title}
                            </span>
                            <span className="font-mono text-[10px] text-white/60 uppercase tracking-widest drop-shadow-md">
                              {variant.subtitle}
                            </span>
                          </div>
                          <div className="flex justify-between items-end">
                            <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                              {formatDate(campaign.createdAt)}
                            </span>
                            <span className="font-mono text-[9px] text-white/50 uppercase tracking-widest drop-shadow-md">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {activeGroup && (
              <div className="mt-12 border border-border rounded-2xl overflow-hidden">
                <div className="px-6 py-5 border-b border-border bg-foreground/2 flex items-center justify-between">
                  <div>
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Segment details</span>
                    <h3 className="mt-2 text-lg font-semibold">
                      {activeGroup.label || `Group ${activeGroup.groupId}`}
                    </h3>
                    {activeGroup.summary && (
                      <p className="mt-2 text-xs text-muted max-w-xl">
                        {activeGroup.summary}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpandedGroup(null)}
                    className="text-xs text-muted hover:text-foreground transition-colors"
                  >
                    Close
                  </button>
                </div>
                <div className="grid gap-0 lg:grid-cols-2">
                  <div className="p-6 border-r border-border">
                    {activeGroup.variantUrl && (
                      <div className="border border-border rounded-xl overflow-hidden bg-foreground/2">
                        <video
                          src={mediaUrl(activeGroup.variantUrl)}
                          controls
                          className="w-full"
                        />
                      </div>
                    )}
                    {activeGroup.changes && activeGroup.changes.length > 0 && (
                      <div className="mt-6">
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Applied transforms
                        </span>
                        <div className="mt-3 flex flex-col gap-0">
                          {activeGroup.changes
                            .filter((c) => c.apply || c.applied)
                            .map((change, ci) => (
                              <div key={ci} className="flex items-start gap-3 border-t border-border py-3">
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
                  <div className="p-6 flex flex-col gap-6">
                    {activeGroup.context && (
                      <div>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Audience context
                        </span>
                        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                          {activeGroup.context.region && (
                            <ContextRow label="Region" value={activeGroup.context.region} />
                          )}
                          {activeGroup.context.country && (
                            <ContextRow label="Country" value={activeGroup.context.country} />
                          )}
                          {activeGroup.context.timeOfDay && (
                            <ContextRow label="Time of day" value={activeGroup.context.timeOfDay} />
                          )}
                          {activeGroup.context.ageBucket && (
                            <ContextRow label="Age bracket" value={activeGroup.context.ageBucket} />
                          )}
                          {activeGroup.context.avgAge != null && (
                            <ContextRow label="Avg age" value={String(activeGroup.context.avgAge)} />
                          )}
                          {activeGroup.context.topGenders && activeGroup.context.topGenders.length > 0 && (
                            <ContextRow label="Top genders" value={activeGroup.context.topGenders.join(", ")} />
                          )}
                          {activeGroup.context.isUrban != null && (
                            <ContextRow label="Urban" value={activeGroup.context.isUrban ? "Yes" : "No"} />
                          )}
                          {activeGroup.context.englishSpeaking != null && (
                            <ContextRow label="English" value={activeGroup.context.englishSpeaking ? "Yes" : "No"} />
                          )}
                        </div>
                        {activeGroup.context.interests && activeGroup.context.interests.length > 0 && (
                          <div className="mt-3">
                            <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                              Interests
                            </span>
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {activeGroup.context.interests.map((interest, ii) => (
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

                    {activeGroup.research?.ok && activeGroup.research.insights && (
                      <div>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Market research
                        </span>
                        <p className="mt-2 text-xs text-muted leading-relaxed whitespace-pre-wrap">
                          {activeGroup.research.insights}
                        </p>
                        {activeGroup.research.citations && activeGroup.research.citations.length > 0 && (
                          <div className="mt-3 flex flex-col gap-1">
                            {activeGroup.research.citations.map((cite, ci) => (
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

                    {activeGroup.planner && (
                      <div>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                          Planner
                        </span>
                        <div className="mt-2 flex items-center gap-2">
                          {activeGroup.planner.ok ? (
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
                              {activeGroup.planner.error || "Partial result"}
                            </span>
                          )}
                          {activeGroup.planner.model && (
                            <span className="text-[10px] text-muted/50 ml-auto">
                              {activeGroup.planner.model}
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
