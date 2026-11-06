"use client";

import React from "react";
import { ChevronDown } from "lucide-react";

/** A collapsible results section: the title and a one-line summary are always
 *  visible, the analysis opens on demand. */
export function ResultSection({
  title,
  summary,
  defaultOpen = false,
  testId,
  children,
}: {
  title: string;
  summary?: React.ReactNode;
  defaultOpen?: boolean;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      data-testid={testId}
      className="group rounded-xl border border-border bg-card shadow-folio"
    >
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 px-6 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl">
        <span>
          <span className="flex items-center gap-2 font-display text-lg font-semibold text-primary">
            <span className="inline-block w-1 h-5 rounded-full bg-accent" aria-hidden="true" />
            {title}
          </span>
          {summary && <span className="mt-1 block text-sm text-muted-foreground">{summary}</span>}
        </span>
        <ChevronDown
          className="mt-1 h-5 w-5 flex-shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="px-6 pb-6">{children}</div>
    </details>
  );
}
