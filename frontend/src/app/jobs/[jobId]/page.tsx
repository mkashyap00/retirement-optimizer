"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { JobStatusCard } from "@/components/JobStatusCard";
import { loadJobMeta, recordJobRun, type JobMeta } from "@/lib/claimSetup";
import { listRuns } from "@/lib/api";
import { latestOptimizedRun } from "@/lib/runs";
import { startOptimization } from "@/lib/startRun";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const [meta, setMeta] = useState<JobMeta | null>(null);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [planLatest, setPlanLatest] = useState<string | null>(null);

  useEffect(() => setMeta(loadJobMeta(jobId)), [jobId]);

  // The plan's newest saved result, for when this job's own outcome is
  // unknown (forgotten by a restart before this page saw it finish).
  useEffect(() => {
    if (!meta || meta.run_id) return;
    let cancelled = false;
    listRuns(meta.household_id)
      .then((runs) => {
        const r = latestOptimizedRun(runs);
        if (!cancelled && r) setPlanLatest(r.run_id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [meta]);

  const savedResults = meta?.run_id
    ? { href: `/results/${meta.run_id}`, label: "View this search's results" }
    : planLatest
      ? { href: `/results/${planLatest}`, label: "View this plan's saved results" }
      : null;

  async function runAgain() {
    if (!meta) return;
    setStarting(true);
    setError(null);
    try {
      const r = await startOptimization({
        householdId: meta.household_id,
        nickname: meta.nickname,
        controls: meta.claim_search,
      });
      if (r.kind === "busy") setBusyJobId(r.jobId);
      else if (r.kind === "job") router.push(`/jobs/${r.jobId}`);
      else router.push(`/results/${r.runId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the search");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-4">
      <JobStatusCard
        // Re-mount per job: "Run again" navigates to a new id.
        key={jobId}
        jobId={jobId}
        title={meta?.nickname}
        onDone={(runId) => {
          recordJobRun(jobId, runId);
          router.push(`/results/${runId}`);
        }}
        savedResults={savedResults}
        onRunAgain={meta ? runAgain : undefined}
        runAgainBusy={starting}
      />
      {busyJobId && (
        <Alert variant="warning">
          <AlertDescription>
            Another search is running.{" "}
            <Link href={`/jobs/${busyJobId}`} className="font-medium underline underline-offset-2">
              View progress
            </Link>
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
