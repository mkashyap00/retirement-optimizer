"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import {
  runProblems,
  searchSummary,
  type ClaimModes,
  type ClaimPreview,
} from "@/lib/claimSetup";

/** A plain statement of the run the per-person claim-age choices produce,
 *  or what must be fixed first. The choices themselves are asked per person
 *  in the wizard's Social Security section. */
export function ClaimAgeSetup({
  preview,
  modes,
  loading,
  error,
}: {
  preview: ClaimPreview | null;
  modes: ClaimModes;
  loading?: boolean;
  error?: string | null;
}) {
  if (error) {
    return (
      <p className="text-sm text-destructive" data-testid="claim-setup-error">
        Could not check claim-age eligibility: {error}
      </p>
    );
  }
  if (!preview) {
    return (
      <p className="text-sm text-muted-foreground flex items-center gap-2" data-testid="claim-setup-loading">
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        Checking which claim ages can be compared…
      </p>
    );
  }
  const summary = searchSummary(preview, modes);
  const problems = runProblems(preview, modes);
  return (
    <div className="space-y-4" data-testid="claim-setup">
      {problems.length > 0 ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
          <p className="font-medium flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4" /> Fix before running:
          </p>
          <ul className="list-disc pl-5 mt-1">
            {problems.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="rounded-md border border-border bg-muted/30 p-3 text-sm space-y-1" data-testid="claim-setup-summary">
          <p className="font-semibold">{summary.headline}</p>
          <p className="text-muted-foreground">{summary.people.join(" · ")}</p>
          {summary.exclusionNote && <p className="text-muted-foreground">{summary.exclusionNote}</p>}
          {summary.comparison && <p className="text-muted-foreground">{summary.comparison}</p>}
          <p className="text-muted-foreground">Estimated time: {summary.estimate}.</p>
        </div>
      )}
      {loading && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin" /> Updating…
        </p>
      )}
    </div>
  );
}
