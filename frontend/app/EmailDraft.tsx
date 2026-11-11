"use client";

import { useId, useState } from "react";

import { API_URL, readError } from "./api";

type Draft = { subject: string; body: string };
type State = "idle" | "loading" | "ready";

export default function EmailDraft({ jobId }: { jobId: string }) {
  const [state, setState] = useState<State>("idle");
  const [draft, setDraft] = useState<Draft>({ subject: "", body: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const subjectId = useId();
  const bodyId = useId();

  async function generate() {
    setState("loading");
    setMessage(null);
    setCopied(false);
    try {
      const res = await fetch(`${API_URL}/meetings/${jobId}/email`, { method: "POST" });
      if (!res.ok) {
        throw new Error(await readError(res, `could not draft the email (status ${res.status})`));
      }
      const data: Draft = await res.json();
      setDraft(data);
      setState("ready");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "could not draft the email");
      // keep an earlier draft on screen if there was one
      setState(draft.body ? "ready" : "idle");
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setMessage("Could not copy automatically, select the text and copy it yourself.");
    }
  }

  const fieldStyle = {
    borderColor: "var(--line)",
    background: "transparent",
    color: "var(--ink)",
  };

  return (
    <section>
      <h2 className="mb-4 text-[13px] font-medium" style={{ color: "var(--ink-soft)" }}>
        Follow up email
      </h2>

      {state === "idle" ? (
        <button
          onClick={generate}
          className="rounded-sm border px-4 py-2 text-[14px] transition-colors hover:bg-[var(--accent-soft)]"
          style={{ borderColor: "var(--line)", color: "var(--ink)" }}
        >
          Draft a follow up email
        </button>
      ) : null}

      {state === "loading" ? (
        <div className="flex items-center gap-3">
          <span
            className="inline-block h-2 w-2 animate-pulse rounded-full"
            style={{ background: "var(--amber)" }}
          />
          <p className="text-[14px]" style={{ color: "var(--ink-soft)" }}>
            Drafting your email, this takes a few seconds
          </p>
        </div>
      ) : null}

      {state === "ready" ? (
        <div className="space-y-4">
          <div>
            <label htmlFor={subjectId} className="mb-1 block text-[13px]" style={{ color: "var(--ink-soft)" }}>
              Subject
            </label>
            <input
              id={subjectId}
              value={draft.subject}
              onChange={(e) => {
                setDraft({ ...draft, subject: e.target.value });
                setCopied(false);
              }}
              className="w-full rounded-sm border px-3 py-2 text-[15px] font-medium"
              style={fieldStyle}
            />
          </div>

          <div>
            <label htmlFor={bodyId} className="mb-1 block text-[13px]" style={{ color: "var(--ink-soft)" }}>
              Message
            </label>
            <textarea
              id={bodyId}
              value={draft.body}
              onChange={(e) => {
                setDraft({ ...draft, body: e.target.value });
                setCopied(false);
              }}
              rows={14}
              className="w-full resize-y rounded-sm border px-3 py-2 text-[15px] leading-relaxed"
              style={fieldStyle}
            />
          </div>

          <div className="flex gap-6 text-[14px]">
            <button
              onClick={copy}
              className="underline underline-offset-4"
              style={{ color: "var(--accent)" }}
            >
              {copied ? "Copied" : "Copy email"}
            </button>
            <button
              onClick={generate}
              className="underline underline-offset-4"
              style={{ color: "var(--ink-soft)" }}
            >
              Draft again
            </button>
          </div>
        </div>
      ) : null}

      {message ? (
        <div
          className="mt-4 rounded-sm px-4 py-3 text-[14px]"
          style={{ background: "var(--red-soft)", color: "var(--red)" }}
        >
          {message}
        </div>
      ) : null}
    </section>
  );
}
