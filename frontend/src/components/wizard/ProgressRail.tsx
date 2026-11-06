"use client";

import React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { label: "Household" },
  { label: "Assumptions" },
  { label: "Accounts" },
  { label: "Income" },
  { label: "Spending" },
  { label: "Review" },
] as const;

interface ProgressRailProps {
  step: number;
  visitedMax: number;
  onStepClick: (step: number) => void;
}

/**
 * Six-node progress rail.
 * - Completed: emerald filled circle with check icon
 * - Active: gold border + gold underline, aria-current="step"
 * - Future: muted circle with number
 * - Clickable only for completed steps (step < current) or visited steps (step <= visitedMax)
 *
 * Desktop: numbered circles with labels
 * Mobile (< lg): compact dots + current step label
 */
export function ProgressRail({ step, visitedMax, onStepClick }: ProgressRailProps) {
  return (
    <nav aria-label="Wizard progress" className="w-full">
      {/* Desktop rail */}
      <ol className="hidden sm:flex items-center w-full">
        {STEPS.map((s, i) => {
          const isCompleted = i < step;
          const isActive = i === step;
          const isVisited = i <= visitedMax;
          const isClickable = isVisited && i !== step;

          return (
            <React.Fragment key={i}>
              <li className="flex flex-col items-center gap-1.5 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => isClickable && onStepClick(i)}
                  disabled={!isClickable}
                  aria-current={isActive ? "step" : undefined}
                  aria-label={`Step ${i + 1}: ${s.label}${isCompleted ? " (completed)" : isActive ? " (current)" : ""}`}
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold font-display transition-all",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    isCompleted &&
                      "bg-primary text-primary-foreground cursor-pointer hover:bg-secondary",
                    isActive &&
                      "border-2 border-accent bg-card text-accent shadow-sm",
                    !isCompleted &&
                      !isActive &&
                      "border-2 border-muted bg-muted/40 text-muted-foreground cursor-default"
                  )}
                >
                  {isCompleted ? (
                    <Check className="w-4 h-4" strokeWidth={2.5} />
                  ) : (
                    <span>{i + 1}</span>
                  )}
                </button>

                <span
                  className={cn(
                    "text-xs font-medium tracking-wide transition-colors",
                    isActive && "text-accent font-semibold",
                    isCompleted && "text-primary",
                    !isCompleted && !isActive && "text-muted-foreground"
                  )}
                >
                  {s.label}
                </span>

                {/* Gold underline for active step */}
                <div
                  className={cn(
                    "h-0.5 w-full transition-all duration-200",
                    isActive ? "bg-accent" : "bg-transparent"
                  )}
                />
              </li>

              {/* Connector line between steps */}
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    "flex-1 h-px mx-2 mb-6 transition-colors duration-300",
                    i < step ? "bg-primary" : "bg-border"
                  )}
                  aria-hidden="true"
                />
              )}
            </React.Fragment>
          );
        })}
      </ol>

      {/* Mobile compact rail: dots + current step label */}
      <div className="sm:hidden flex items-center gap-3 px-1">
        <div className="flex items-center gap-1.5">
          {STEPS.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => i <= visitedMax && i !== step && onStepClick(i)}
              disabled={i > visitedMax || i === step}
              aria-current={i === step ? "step" : undefined}
              aria-label={`Step ${i + 1}`}
              className={cn(
                "rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                i === step
                  ? "w-5 h-5 bg-accent"
                  : i < step
                  ? "w-3 h-3 bg-primary cursor-pointer"
                  : "w-3 h-3 bg-muted"
              )}
            />
          ))}
        </div>
        <span className="text-sm font-semibold text-foreground font-display">
          {STEPS[step]?.label}
        </span>
        <span className="text-xs text-muted-foreground ml-auto">
          {step + 1} / {STEPS.length}
        </span>
      </div>
    </nav>
  );
}
