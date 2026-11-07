"use client";

import { useEffect, useState } from "react";

import { API_URL, readError } from "./api";

type MeetingSummary = {
  job_id: string;
  filename: string;
  status: string;
  created_at: string;
};

type Props = {
  onOpen: (jobId: string, filename: string) => void;
  onRetried: (jobId: string, filename: string) => void;
};

// The backend stores UTC times but sends them without a timezone marker,
// so add one, otherwise the browser would read them as local time.
function formatCreatedAt(value: string): string {
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function statusColor(status: string): string {
  if (status === "completed") return "var(--accent)";
  if (status === "failed") return "var(--red)";
  return "var(--amber)";
}

export default function PastMeetings({ onOpen, onRetried }: Props) {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch(`${API_URL}/meetings?limit=20`);
        if (!res.ok) throw new Error(`server responded with ${res.status}`);
        const data: MeetingSummary[] = await res.json();
        if (!cancelled) setMeetings(data);
      } catch {
        if (!cancelled) {
          setMeetings([]);
          setMessage("Could not load past meetings.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleRetry(meeting: MeetingSummary) {
    setPendingId(meeting.job_id);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/meetings/${meeting.job_id}/retry`, { method: "POST" });
      if (!res.ok) throw new Error(await readError(res, `retry failed with status ${res.status}`));
      onRetried(meeting.job_id, meeting.filename);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "retry failed");
      setPendingId(null);
    }
  }

  async function handleDelete(meeting: MeetingSummary) {
    if (!window.confirm(`Delete ${meeting.filename} and all of its results?`)) return;

    setPendingId(meeting.job_id);
    setMessage(null);
    try {
      const res = await fetch(`${API_URL}/meetings/${meeting.job_id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await readError(res, `delete failed with status ${res.status}`));
      setMeetings((current) => (current ?? []).filter((m) => m.job_id !== meeting.job_id));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "delete failed");
    } finally {
      setPendingId(null);
    }
  }

  if (meetings === null) return null;
  if (meetings.length === 0 && !message) return null;

  return (
    <section className="mt-16">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
          Past meetings
        </h2>
        <span className="text-[13px]" style={{ color: "var(--ink-soft)" }}>
          {meetings.length}
        </span>
      </div>

      {message ? (
        <div
          className="mb-4 rounded-sm px-4 py-3 text-[14px]"
          style={{ background: "var(--red-soft)", color: "var(--red)" }}
        >
          {message}
        </div>
      ) : null}

      <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
        {meetings.map((meeting) => {
          const isPending = pendingId === meeting.job_id;
          const isProcessing = meeting.status === "processing";

          return (
            <li
              key={meeting.job_id}
              className="flex items-center justify-between gap-4 py-3"
              style={{ borderColor: "var(--line)" }}
            >
              <div className="min-w-0">
                <p className="truncate text-[15px]" style={{ color: "var(--ink)" }}>
                  {meeting.filename}
                </p>
                <p className="mt-1 text-[13px]" style={{ color: "var(--ink-soft)" }}>
                  {formatCreatedAt(meeting.created_at)}
                  {" · "}
                  <span style={{ color: statusColor(meeting.status) }}>{meeting.status}</span>
                </p>
              </div>

              <div className="flex shrink-0 gap-4 text-[14px]">
                {meeting.status === "completed" ? (
                  <button
                    onClick={() => onOpen(meeting.job_id, meeting.filename)}
                    disabled={isPending}
                    className="underline underline-offset-4 disabled:opacity-50"
                    style={{ color: "var(--accent)" }}
                  >
                    Open
                  </button>
                ) : null}
                {meeting.status === "failed" ? (
                  <button
                    onClick={() => handleRetry(meeting)}
                    disabled={isPending}
                    className="underline underline-offset-4 disabled:opacity-50"
                    style={{ color: "var(--accent)" }}
                  >
                    Retry
                  </button>
                ) : null}
                {!isProcessing ? (
                  <button
                    onClick={() => handleDelete(meeting)}
                    disabled={isPending}
                    className="underline underline-offset-4 disabled:opacity-50"
                    style={{ color: "var(--ink-soft)" }}
                  >
                    Delete
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
