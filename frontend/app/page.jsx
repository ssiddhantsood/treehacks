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

  return (
    <main className="page">
      <h1>Video Speedup</h1>
      <p>Upload a video and get changed versions plus a basic action timeline.</p>

      {!user ? (
        <form onSubmit={handleAuth} className="row">
          <input
            type="email"
            placeholder="email"
            value={authEmail}
            onChange={e => setAuthEmail(e.target.value)}
          />
          <input
            type="password"
            placeholder="password"
            value={authPassword}
            onChange={e => setAuthPassword(e.target.value)}
          />
          <button type="submit">{authMode === "register" ? "Register" : "Login"}</button>
          <button
            type="button"
            onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
          >
            {authMode === "register" ? "Use Login" : "Use Register"}
          </button>
        </form>
      ) : (
        <div className="row">
          <span className="status">Signed in as {user.email}</span>
          <button
            type="button"
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

      {user ? (
        <form onSubmit={handleSubmit} className="row">
          <input ref={inputRef} type="file" accept="video/*" />
          <button type="submit">Process</button>
          <span className="status">{status}</span>
        </form>
      ) : null}

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section>
          <h2>Your Videos</h2>
          {videos.length === 0 ? (
            <div className="box">No videos yet.</div>
          ) : (
            <div className="timeline">
              {videos.map(video => (
                <button
                  key={video.id}
                  type="button"
                  className={`timeline-item${selectedVideoId === video.id ? " active" : ""}`}
                  onClick={() => loadVideo(video.id)}
                >
                  <span>{video.id.slice(0, 6)}</span>
                  <span>{video.createdAt}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section>
          <h2>Original</h2>
          {originalUrl ? <video ref={videoRef} src={originalUrl} controls /> : <div className="box">No video</div>}
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
