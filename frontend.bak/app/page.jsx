"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Home() {
  const inputRef = useRef(null);
  const videoRef = useRef(null);

  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMode, setAuthMode] = useState("login");
  const [videos, setVideos] = useState([]);
  const [selectedVideoId, setSelectedVideoId] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [originalUrl, setOriginalUrl] = useState("");
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
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || payload.error || "Upload failed");
      }

      const payload = await response.json();
      setOriginalUrl(`${API_BASE}${payload.originalUrl}`);
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

      if (payload.videoId) {
        setSelectedVideoId(payload.videoId);
        await fetchVideos();
      }

      setStatus("done");
    } catch (err) {
      setStatus("error");
      setError(err.message || "Something went wrong");
    }
  };

  const fetchVideos = async () => {
    if (!token) return;
    const response = await fetch(`${API_BASE}/api/videos`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!response.ok) return;
    const payload = await response.json();
    setVideos(payload.videos || []);
  };

  const loadVideo = async videoId => {
    if (!token || !videoId) return;
    const response = await fetch(`${API_BASE}/api/videos/${videoId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!response.ok) return;
    const payload = await response.json();
    const video = payload.video;
    setSelectedVideoId(video.id);
    setOriginalUrl(`${API_BASE}${video.originalUrl}`);
    setAnalysis(null);
    if (video.analysisUrl) {
      const analysisResponse = await fetch(`${API_BASE}${video.analysisUrl}`);
      const analysisPayload = await analysisResponse.json();
      setAnalysis(analysisPayload);
    }
    setVariants(
      (video.variants || []).map(item => ({
        name: item.name,
        url: `${API_BASE}${item.url}`
      }))
    );
  };

  const handleAuth = async event => {
    event.preventDefault();
    setError("");
    const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: authEmail, password: authPassword })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Auth failed");
      return;
    }
    const payload = await response.json();
    const newToken = payload.token;
    setToken(newToken);
    localStorage.setItem("auth_token", newToken);
    setUser(payload.user);
    await fetchVideos();
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;

    const onTimeUpdate = () => setCurrentTime(video.currentTime || 0);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, [originalUrl]);

  useEffect(() => {
    const stored = localStorage.getItem("auth_token");
    if (!stored) return;
    setToken(stored);
  }, []);

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/api/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => (res.ok ? res.json() : null))
      .then(payload => {
        if (payload?.user) {
          setUser(payload.user);
          fetchVideos();
        }
      })
      .catch(() => {});
  }, [token]);

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

  const statusLabel =
    status === "uploading"
      ? "Processing"
      : status === "done"
        ? "Complete"
        : status === "error"
          ? "Error"
          : "Idle";
  const videoCardCount = (originalUrl ? 1 : 0) + variants.length;

  return (
    <main className="page">
      <header className="hero">
        <div className="hero-copy reveal">
          <span className="eyebrow">PERSONALIZED ADS</span>
          <h1>Personalized Ad Generator</h1>
          <p>
            Upload product footage, generate tailored ad variants, and jump through a smart
            highlight timeline.
          </p>
          <div className="hero-metrics">
            <div className="metric">
              <span className="metric-label">Status</span>
              <span className="metric-value">{statusLabel}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Session</span>
              <span className="metric-value">{user ? "Signed In" : "Guest"}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Library</span>
              <span className="metric-value">{videos.length} videos</span>
            </div>
          </div>
        </div>
        <div className="hero-card reveal delay-1">
          {!user ? (
            <div className="stack">
              <div>
                <span className="eyebrow">Access</span>
                <h2>Access the generator</h2>
                <p className="muted">
                  Create an account or sign in to generate ads and keep a personal library.
                </p>
              </div>
              <form onSubmit={handleAuth} className="stack">
                <input
                  type="email"
                  placeholder="Email address"
                  value={authEmail}
                  onChange={e => setAuthEmail(e.target.value)}
                  className="input"
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={authPassword}
                  onChange={e => setAuthPassword(e.target.value)}
                  className="input"
                />
                <div className="form-actions">
                  <button type="submit" className="btn btn-primary">
                    {authMode === "register" ? "Create account" : "Sign in"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
                  >
                    {authMode === "register" ? "Use sign in" : "Use register"}
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <div className="stack">
              <div>
                <span className="eyebrow">Signed In</span>
                <h2>{user.email}</h2>
                <p className="muted">Upload new footage or revisit past ad renders.</p>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  localStorage.removeItem("auth_token");
                  setToken("");
                  setUser(null);
                  setVideos([]);
                  setSelectedVideoId("");
                }}
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </header>

      {error ? <div className="error reveal">{error}</div> : null}

      <section className="panel upload-panel reveal delay-2">
        <div className="panel-header">
          <div>
            <h2>Upload & Generate</h2>
            <p className="muted">
              Create a clean master cut, personalized variants, and a quick highlight timeline.
            </p>
          </div>
          <span className={`status-chip ${status}`}>{statusLabel}</span>
        </div>
        {user ? (
          <form onSubmit={handleSubmit} className="upload-form">
            <input ref={inputRef} type="file" accept="video/*" className="file-input" />
            <button type="submit" className="btn btn-primary">
              Generate ads
            </button>
          </form>
        ) : (
          <div className="panel-empty">Sign in to upload footage and generate ad variants.</div>
        )}
      </section>

      <section className="video-gallery full-bleed reveal">
        <div className="video-gallery-header">
          <div>
            <span className="eyebrow">FULL-SCREEN PREVIEW</span>
            <h2>Video Cards</h2>
            <p className="muted">
              Each video renders as a full-screen card with space for rich metadata on the side.
            </p>
          </div>
          <span className="pill">{videoCardCount} cards</span>
        </div>
        {videoCardCount === 0 ? (
          <div className="panel-empty">Upload footage to see full-screen video cards.</div>
        ) : (
          <div className="video-cards">
            {originalUrl ? (
              <article className="video-card">
                <div className="video-card-media">
                  <span className="eyebrow">Source Footage</span>
                  <div className="video-card-title">Master Cut</div>
                  <div className="video-frame">
                    <video ref={videoRef} src={originalUrl} controls />
                  </div>
                </div>
                <aside className="video-card-meta">
                  <div>
                    <h3>Descriptions</h3>
                    <p className="muted">
                      Metadata, targeting notes, and creative context will live here soon.
                    </p>
                  </div>
                  <div className="meta-lines">
                    <div className="meta-line" />
                    <div className="meta-line" />
                    <div className="meta-line short" />
                  </div>
                  <div className="meta-grid">
                    <div className="meta-block">
                      <span className="meta-label">Audience</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">Goal</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">Format</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">Notes</span>
                      <span className="meta-value">—</span>
                    </div>
                  </div>
                </aside>
              </article>
            ) : null}
            {variants.map(variant => (
              <article key={variant.url} className="video-card">
                <div className="video-card-media">
                  <span className="eyebrow">Ad Variant</span>
                  <div className="video-card-title">{variant.name}</div>
                  <div className="video-frame">
                    <video src={variant.url} controls />
                  </div>
                </div>
                <aside className="video-card-meta">
                  <div>
                    <h3>Descriptions</h3>
                    <p className="muted">
                      Keep variant-specific messaging, hooks, and performance notes here.
                    </p>
                  </div>
                  <div className="meta-lines">
                    <div className="meta-line" />
                    <div className="meta-line" />
                    <div className="meta-line short" />
                  </div>
                  <div className="meta-grid">
                    <div className="meta-block">
                      <span className="meta-label">Persona</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">Message</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">CTA</span>
                      <span className="meta-value">—</span>
                    </div>
                    <div className="meta-block">
                      <span className="meta-label">Notes</span>
                      <span className="meta-value">—</span>
                    </div>
                  </div>
                </aside>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="grid">
        <section className="panel reveal">
          <div className="panel-header">
            <h2>Your Projects</h2>
            <span className="pill">{videos.length} items</span>
          </div>
          {videos.length === 0 ? (
            <div className="panel-empty">No projects yet.</div>
          ) : (
            <div className="timeline">
              {videos.map(video => (
                <button
                  key={video.id}
                  type="button"
                  className={`timeline-item${selectedVideoId === video.id ? " active" : ""}`}
                  onClick={() => loadVideo(video.id)}
                >
                  <span className="timecode">{video.id.slice(0, 6)}</span>
                  <span className="caption">{video.createdAt}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="panel reveal">
          <div className="panel-header">
            <h2>Highlights</h2>
            <span className="pill">{analysis ? timelineEvents.length : 0} cues</span>
          </div>
          {!analysis ? (
            <div className="panel-empty">Upload footage to generate highlights.</div>
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
                    <span className="timecode">{formatTime(event.t_start)}</span>
                    <span className="caption">{event.caption}</span>
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
