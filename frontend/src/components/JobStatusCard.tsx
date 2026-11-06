"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, Loader2, AlertTriangle } from "lucide-react";
import { getOptimizeJob } from "@/lib/api";
import { isApiError } from "@/lib/apiError";
import type { OptimizeJob } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const POLL_MS = 2000;
/** Longest wait between polls while the server is unreachable. */
const MAX_BACKOFF_MS = 10000;

/** The four stages a search goes through, in the words the user sees. The
 *  backend's phases map onto the first three; the fourth is the save. */
export const STAGES = [
  { phase: "deterministic", label: "Compare strategies", unit: "claim-age pairs" },
  { phase: "monte_carlo", label: "Test market outcomes", unit: "batches" },
  { phase: "sensitivity", label: "Check longevity", unit: "checks" },
  { phase: "prepare", label: "Prepare results", unit: "" },
] as const;

type View =
  | { kind: "polling"; job: OptimizeJob | null; reconnecting: boolean }
  | { kind: "done"; job: OptimizeJob }
  | { kind: "failed"; job: OptimizeJob }
  | { kind: "gone" };

function stageIndex(job: OptimizeJob | null): number {
  if (!job) return 0;
  if (job.status === "done") return 3;
  const i = STAGES.findIndex((s) => s.phase === job.phase);
  return i < 0 ? 0 : i;
}

function elapsed(fromIso: string | null | undefined, now: number): string {
  if (!fromIso) return "";
  const s = Math.max(0, Math.round((now - new Date(fromIso).getTime()) / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min ${String(s % 60).padStart(2, "0")} s` : `${s} s`;
}

/** Polls a job until it finishes and says, at every point, what is happening
 *  and what the user can do. A failed poll is a reconnect (it never starts a
 *  new job). A 404 only means the server no longer knows the job: jobs live
 *  in memory, so a restart forgets finished ones too -- whose results are
 *  saved. Hence "check saved results", never "results lost". */
export function JobStatusCard({
  jobId,
  title,
  onDone,
  onRunAgain,
  runAgainBusy,
  savedResults,
}: {
  jobId: string;
  title?: string | null;
  onDone?: (runId: string) => void;
  /** Absent when the job's inputs are unknown (then: back to the dashboard). */
  onRunAgain?: () => void;
  runAgainBusy?: boolean;
  /** Where this search's (or this plan's) saved results are, when known. */
  savedResults?: { href: string; label: string } | null;
}) {
  const [view, setView] = useState<View>({ kind: "polling", job: null, reconnecting: false });
  const [now, setNow] = useState(() => Date.now());
  const [announcement, setAnnouncement] = useState("");
  const done = useRef(onDone);
  done.current = onDone;
  const lastAnnounced = useRef("");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let backoff = POLL_MS;
    const tick = async () => {
      try {
        const job = await getOptimizeJob(jobId);
        if (stopped) return;
        backoff = POLL_MS;
        if (job.status === "done" && job.run_id) {
          setView({ kind: "done", job });
          done.current?.(job.run_id);
          return;
        }
        if (job.status === "failed") {
          setView({ kind: "failed", job });
          return;
        }
        setView({ kind: "polling", job, reconnecting: false });
      } catch (e) {
        if (stopped) return;
        if (isApiError(e, 404)) {
          setView({ kind: "gone" });
          return;
        }
        // Unreachable or a transient error: keep the last state, say so, retry.
        setView((v) => (v.kind === "polling" ? { ...v, reconnecting: true } : v));
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      }
      timer = setTimeout(tick, backoff);
    };
    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Announce stage changes and the outcome -- not every poll.
  const stage = view.kind === "polling" ? STAGES[stageIndex(view.job)].label : view.kind;
  useEffect(() => {
    const text =
      view.kind === "done"
        ? "Search complete. Results are ready."
        : view.kind === "failed"
          ? "The search failed."
          : view.kind === "gone"
            ? "The search status is no longer available."
            : `Now: ${stage}.`;
    if (text !== lastAnnounced.current) {
      lastAnnounced.current = text;
      setAnnouncement(text);
    }
  }, [view.kind, stage]);

  const job = view.kind === "gone" ? null : view.job;
  const current = view.kind === "done" ? 4 : stageIndex(job);

  return (
    <Card className="shadow-folio border-border max-w-2xl" data-testid="job-status">
      <span className="sr-only" aria-live="polite" data-testid="job-announcement">
        {announcement}
      </span>
      <CardHeader>
        <CardTitle className="font-display text-lg text-primary">
          {title ? `${title} — ` : ""}Optimizing conversions and claim ages
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ol className="space-y-2" data-testid="job-stages">
          {STAGES.map((s, i) => {
            const state = i < current ? "done" : i === current ? "current" : "todo";
            const showCount =
              state === "current" && view.kind === "polling" && job && job.progress.total > 0 && s.unit;
            return (
              <li key={s.phase} className="flex items-center gap-2 text-sm" data-state={state}>
                {state === "done" ? (
                  <CheckCircle2 className="h-4 w-4 text-secondary" aria-hidden="true" />
                ) : state === "current" && view.kind === "polling" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/50" aria-hidden="true" />
                )}
                <span className={state === "todo" ? "text-muted-foreground" : "font-medium"}>
                  {s.label}
                </span>
                {showCount && (
                  <span className="text-muted-foreground tabular-nums" data-testid="job-stage-count">
                    — {job!.progress.done} of {job!.progress.total} {s.unit}
                  </span>
                )}
                <span className="sr-only">
                  {state === "done" ? "(finished)" : state === "current" ? "(in progress)" : "(not started)"}
                </span>
              </li>
            );
          })}
        </ol>

        {view.kind === "polling" && (
          <div className="space-y-1 text-sm text-muted-foreground">
            <p data-testid="job-elapsed">
              Elapsed: {elapsed(job?.started_at ?? job?.created_at, now) || "starting…"}
            </p>
            {view.reconnecting && (
              <p className="text-amber-700" data-testid="job-reconnecting">
                Reconnecting… checking the search status.
              </p>
            )}
            <p>You can leave this page. The search continues while the server is running.</p>
          </div>
        )}

        {view.kind === "done" && (
          <div className="space-y-2">
            <p className="text-sm">The search finished.</p>
            <Button asChild data-testid="job-view-results">
              <Link href={`/results/${view.job.run_id}`}>View results</Link>
            </Button>
          </div>
        )}

        {view.kind === "failed" && (
          <div className="space-y-2" role="alert">
            <p className="text-sm text-destructive flex items-start gap-1.5" data-testid="job-error">
              <AlertTriangle className="h-4 w-4 mt-0.5" aria-hidden="true" />
              {view.job.error?.startsWith("interrupted")
                ? "The search stopped because the server was shut down. Nothing was saved."
                : `The search failed: ${view.job.error ?? "unknown error"}.`}
            </p>
            <RecoveryActions onRunAgain={onRunAgain} busy={runAgainBusy} savedResults={savedResults} />
          </div>
        )}

        {view.kind === "gone" && (
          <div className="space-y-2" role="alert">
            <p className="text-sm" data-testid="job-error">
              This search&apos;s status is no longer available. Check saved results before
              running again.
            </p>
            <RecoveryActions onRunAgain={onRunAgain} busy={runAgainBusy} savedResults={savedResults} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RecoveryActions({
  onRunAgain,
  busy,
  savedResults,
}: {
  onRunAgain?: () => void;
  busy?: boolean;
  savedResults?: { href: string; label: string } | null;
}) {
  return (
    <div className="flex gap-2 flex-wrap">
      {savedResults && (
        <Button asChild data-testid="job-saved-results">
          <Link href={savedResults.href}>{savedResults.label}</Link>
        </Button>
      )}
      {onRunAgain && (
        <Button
          variant={savedResults ? "outline" : "default"}
          onClick={onRunAgain}
          disabled={busy}
          data-testid="job-run-again"
        >
          {busy ? "Starting…" : "Run again"}
        </Button>
      )}
      <Button variant="outline" asChild>
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
