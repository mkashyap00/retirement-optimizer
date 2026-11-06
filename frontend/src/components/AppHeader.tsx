"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getActiveOptimizeJob } from "@/lib/api";
import type { OptimizeJob } from "@/lib/types";

const ACTIVE_POLL_MS = 10000;

/** "Search running · View progress" on every page while a claim-age search
 *  runs, so leaving the progress page never loses it. */
function ActiveJobIndicator({ pathname }: { pathname: string }) {
  const [job, setJob] = useState<OptimizeJob | null>(null);
  useEffect(() => {
    let stopped = false;
    const check = () =>
      getActiveOptimizeJob()
        .then((j) => !stopped && setJob(j ?? null))
        .catch(() => {}); // the indicator is a convenience; stay quiet offline
    check();
    const t = setInterval(check, ACTIVE_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [pathname]);
  if (!job || pathname === `/jobs/${job.id}`) return null;
  return (
    <Link
      href={`/jobs/${job.id}`}
      data-testid="active-job-indicator"
      className="flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-medium text-primary hover:bg-accent/20"
    >
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      Search running · View progress
    </Link>
  );
}

const NAV_LINKS = [
  { href: "/",          label: "Dashboard" },
  { href: "/compare",   label: "What-if"   },
  { href: "/portfolio", label: "Portfolio" },
] as const;

export function AppHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 bg-card border-b border-border shadow-folio">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Wordmark */}
        <Link
          href="/"
          className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
          aria-label="Retirement Optimizer home"
        >
          {/* Gold vertical accent bar — the signature detail */}
          <span
            className="inline-block w-1 h-5 rounded-full bg-accent"
            aria-hidden="true"
          />
          <span className="font-display font-semibold text-primary text-base tracking-tight leading-none">
            Retirement Optimizer
          </span>
        </Link>

        <div className="flex items-center gap-4">
        <ActiveJobIndicator pathname={pathname} />
        {/* Primary navigation */}
        <nav aria-label="Primary navigation">
          <ul className="flex items-center gap-1">
            {NAV_LINKS.map(({ href, label }) => {
              const isActive =
                href === "/"
                  ? pathname === "/"
                  : pathname === href || pathname.startsWith(href + "/");
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={isActive ? "page" : undefined}
                    className={[
                      "px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors",
                      isActive
                        ? "text-primary bg-primary/8"
                        : "text-foreground/60 hover:text-foreground hover:bg-muted",
                    ].join(" ")}
                  >
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        </div>
      </div>
    </header>
  );
}
