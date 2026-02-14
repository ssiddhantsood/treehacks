"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Home() {
  const inputRef = useRef(null);
  const videoRef = useRef(null);

  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [originalUrl, setOriginalUrl] = useState("");
  const [processedUrl, setProcessedUrl] = useState("");
  const [variants, setVariants] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);

  const handleSubmit = async event => {
    event.preventDefault();
    setError("");
    setStatus("uploading");
    setAnalysis(null);
    setVariants([]);

    const file = inputRef.current?.files?.[0];
    if (!file) {
      setStatus("idle");
      setError("Select a video file");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("video", file);

      const response = await fetch(`${API_BASE}/api/transform`, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || payload.error || "Upload failed");
      }

      const payload = await response.json();
      setOriginalUrl(`${API_BASE}${payload.originalUrl}`);
      setProcessedUrl(`${API_BASE}${payload.processedUrl}`);
      if (Array.isArray(payload.variants)) {
        setVariants(
          payload.variants.map(item => ({
            name: item.name,
            url: `${API_BASE}${item.url}`
          }))
        );
      }

      if (payload.analysisUrl) {
        const analysisResponse = await fetch(`${API_BASE}${payload.analysisUrl}`);
        const analysisPayload = await analysisResponse.json();
        setAnalysis(analysisPayload);
      }

      setStatus("done");
    } catch (err) {
      setStatus("error");
      setError(err.message || "Something went wrong");
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;

    const onTimeUpdate = () => setCurrentTime(video.currentTime || 0);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, [originalUrl]);

  const timelineEvents = useMemo(() => {
    if (!analysis?.events || !analysis?.captions) return [];
    const captions = new Map(analysis.captions.map(item => [item.id, item]));
    return analysis.events.map(event => ({
      ...event,
      caption: captions.get(event.caption_id)?.caption || "No description"
    }));
  }, [analysis]);

  const formatTime = seconds => {
    const total = Math.max(0, Math.floor(seconds));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <main className="page">
      <h1>Video Speedup</h1>
      <p>Upload a video and get a +5% version plus a basic action timeline.</p>

      <form onSubmit={handleSubmit} className="row">
        <input ref={inputRef} type="file" accept="video/*" />
        <button type="submit">Process</button>
        <span className="status">{status}</span>
      </form>

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section>
          <h2>Original</h2>
          {originalUrl ? <video ref={videoRef} src={originalUrl} controls /> : <div className="box">No video</div>}
        </section>

        <section>
          <h2>Speed +5%</h2>
          {processedUrl ? <video src={processedUrl} controls /> : <div className="box">No video</div>}
        </section>

        <section>
          <h2>Variants</h2>
          {variants.length === 0 ? (
            <div className="box">No variants yet.</div>
          ) : (
            <div className="variants">
              {variants.map(variant => (
                <div key={variant.url} className="variant">
                  <div className="variant-title">{variant.name}</div>
                  <video src={variant.url} controls />
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h2>Timeline</h2>
          {!analysis ? (
            <div className="box">Upload a video to see actions.</div>
          ) : (
            <div className="timeline">
              {timelineEvents.map(event => {
                const active = currentTime >= event.t_start && currentTime < event.t_end;
                return (
                  <button
                    key={`${event.t_start}-${event.caption_id}`}
                    type="button"
                    className={`timeline-item${active ? " active" : ""}`}
                    onClick={() => {
                      if (videoRef.current) {
                        videoRef.current.currentTime = event.t_start;
                        videoRef.current.play();
                      }
                    }}
                  >
                    <span>{formatTime(event.t_start)}</span>
                    <span>{event.caption}</span>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
