"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Segment = { start: number; end: number; text: string };
type ActionItem = { description: string; owner: string | null; due_date: string | null };
type TimelineEvent = { topic: string; summary: string; approx_time: string | null };
type Decision = { decision: string; context: string | null };
type Status = "idle" | "uploading" | "processing" | "completed" | "failed";

type MeetingResult = {
  job_id: string;
  status: string;
  text: string | null;
  language: string | null;
  segments: Segment[];
  action_items: ActionItem[];
  timeline: TimelineEvent[];
  decisions: Decision[];
  error: string | null;
};

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<MeetingResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const pollJob = useCallback((jobId: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/meetings/${jobId}`);
        if (!res.ok) throw new Error(`server responded with ${res.status}`);
        const data: MeetingResult = await res.json();

        if (data.status === "completed") {
          setResult(data);
          setStatus("completed");
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (data.status === "failed") {
          setErrorMessage(data.error ?? "processing failed for an unknown reason");
          setStatus("failed");
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "could not reach the server");
        setStatus("failed");
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 3000);
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setFileName(file.name);
      setResult(null);
      setErrorMessage(null);
      setStatus("uploading");

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`${API_URL}/meetings/upload`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) throw new Error(`upload failed with status ${res.status}`);
        const data = await res.json();
        setStatus("processing");
        pollJob(data.job_id);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "upload failed");
        setStatus("failed");
      }
    },
    [pollJob]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const isBusy = status === "uploading" || status === "processing";

  return (
    <div className="mx-auto max-w-[720px] px-6 py-16">
      <header className="mb-12">
        <h1 className="text-[28px] font-medium tracking-tight" style={{ color: "var(--ink)" }}>
          Meeting Intelligence
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
          Upload a recording. Get a transcript and the action items out of it.
        </p>
      </header>

      {status === "idle" || status === "failed" ? (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer rounded-sm border border-dashed px-8 py-14 text-center transition-colors hover:bg-[var(--accent-soft)]"
          style={{ borderColor: "var(--line)" }}
        >
          <p className="text-[15px]" style={{ color: "var(--ink)" }}>
            Drop an audio file here, or click to choose one
          </p>
          <p className="mt-1 text-[13px]" style={{ color: "var(--ink-soft)" }}>
            .mp3, .m4a, .wav
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </div>
      ) : null}

      {errorMessage ? (
        <div
          className="mt-6 rounded-sm px-4 py-3 text-[14px]"
          style={{ background: "var(--red-soft)", color: "var(--red)" }}
        >
          {errorMessage}
        </div>
      ) : null}

      {isBusy ? (
        <div className="mt-10 flex items-center gap-3">
          <span
            className="inline-block h-2 w-2 animate-pulse rounded-full"
            style={{ background: "var(--amber)" }}
          />
          <p className="text-[14px]" style={{ color: "var(--ink-soft)" }}>
            {status === "uploading"
              ? `Uploading ${fileName}`
              : `Processing ${fileName}, this can take a few minutes`}
          </p>
        </div>
      ) : null}

      {result && status === "completed" ? (
        <div className="mt-12 space-y-12">
          <section>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
                Action items
              </h2>
              <span className="text-[13px]" style={{ color: "var(--ink-soft)" }}>
                {result.action_items.length}
              </span>
            </div>

            {result.action_items.length === 0 ? (
              <p className="text-[14px]" style={{ color: "var(--ink-soft)" }}>
                No action items were found in this recording.
              </p>
            ) : (
              <ul className="space-y-3">
                {result.action_items.map((item, i) => (
                  <li
                    key={i}
                    className="border-l-2 pl-4"
                    style={{ borderColor: "var(--accent)" }}
                  >
                    <p className="text-[15px]" style={{ color: "var(--ink)" }}>
                      {item.description}
                    </p>
                    {(item.owner || item.due_date) && (
                      <p className="mt-1 text-[13px]" style={{ color: "var(--ink-soft)" }}>
                        {[item.owner, item.due_date].filter(Boolean).join(" · ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
                Decisions
              </h2>
              <span className="text-[13px]" style={{ color: "var(--ink-soft)" }}>
                {result.decisions.length}
              </span>
            </div>

            {result.decisions.length === 0 ? (
              <p className="text-[14px]" style={{ color: "var(--ink-soft)" }}>
                No clear decisions were made in this recording.
              </p>
            ) : (
              <ul className="space-y-3">
                {result.decisions.map((item, i) => (
                  <li key={i} className="border-l-2 pl-4" style={{ borderColor: "var(--amber)" }}>
                    <p className="text-[15px]" style={{ color: "var(--ink)" }}>
                      {item.decision}
                    </p>
                    {item.context && (
                      <p className="mt-1 text-[13px]" style={{ color: "var(--ink-soft)" }}>
                        {item.context}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
              Timeline
            </h2>

            {result.timeline.length === 0 ? (
              <p className="text-[14px]" style={{ color: "var(--ink-soft)" }}>
                No distinct topics were identified in this recording.
              </p>
            ) : (
              <ol className="space-y-4">
                {result.timeline.map((event, i) => (
                  <li key={i} className="flex gap-4">
                    <span
                      className="mt-[2px] shrink-0 font-mono text-[12px]"
                      style={{ color: "var(--ink-soft)" }}
                    >
                      {event.approx_time ?? "—"}
                    </span>
                    <div>
                      <p className="text-[15px] font-medium" style={{ color: "var(--ink)" }}>
                        {event.topic}
                      </p>
                      <p className="mt-1 text-[14px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
                        {event.summary}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
              Transcript
            </h2>
            <div className="space-y-4">
              {result.segments.map((segment, i) => (
                <div key={i} className="flex gap-4">
                  <span
                    className="mt-[2px] shrink-0 font-mono text-[12px]"
                    style={{ color: "var(--ink-soft)" }}
                  >
                    {formatTime(segment.start)}
                  </span>
                  <p className="text-[15px] leading-relaxed" style={{ color: "var(--ink)" }}>
                    {segment.text}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <button
            onClick={() => {
              setStatus("idle");
              setResult(null);
              setFileName(null);
              if (fileInputRef.current) fileInputRef.current.value = "";
            }}
            className="text-[14px] underline underline-offset-4"
            style={{ color: "var(--accent)" }}
          >
            Upload another recording
          </button>
        </div>
      ) : null}
    </div>
  );
}
