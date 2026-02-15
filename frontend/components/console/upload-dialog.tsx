"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function UploadForm() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [error, setError] = useState("");

  const handleUpload = async () => {
    const file = inputRef.current?.files?.[0];
    if (!file) return;

    setStatus("uploading");
    setError("");

    try {
      const res = await api.videos.upload(file);
      setStatus("done");
      router.push(`/console/campaigns/${res.videoId}`);
      router.refresh();
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          className="text-sm text-muted file:mr-3 file:border file:border-border file:bg-transparent file:px-3 file:py-1.5 file:font-mono file:text-[11px] file:uppercase file:tracking-widest file:text-foreground file:cursor-pointer hover:file:text-white"
        />
        <Button
          onClick={handleUpload}
          disabled={status === "uploading"}
          size="sm"
        >
          {status === "uploading" ? "Processing..." : "Upload"}
        </Button>
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
