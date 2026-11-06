"use client";

import React, { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Text input with optional adornment (prefix / suffix). */
export function AdornedInput({
  prefix,
  suffix,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  prefix?: string;
  suffix?: string;
}) {
  if (!prefix && !suffix) {
    return (
      <Input
        className={cn(className)}
        {...props}
      />
    );
  }
  return (
    <div className="relative flex items-center">
      {prefix && (
        <span className="absolute left-3 text-sm text-muted-foreground pointer-events-none select-none z-10">
          {prefix}
        </span>
      )}
      <Input
        className={cn(prefix && "pl-7", suffix && "pr-7", className)}
        {...props}
      />
      {suffix && (
        <span className="absolute right-3 text-sm text-muted-foreground pointer-events-none select-none">
          {suffix}
        </span>
      )}
    </div>
  );
}

/** The amount typed or pasted, read the same way while typing and on blur:
 *  "$10,000", "10000" and "-10,000" are all 10000. Amounts here are never
 *  negative; a field that needs a sign (a loss) asks for it separately. */
export function parseAmount(text: string): number | undefined {
  const n = parseFloat(text.replace(/[^0-9.]/g, ""));
  return isNaN(n) ? undefined : n;
}

/**
 * Currency input with $ prefix.
 * Shows Intl-formatted value on blur, raw number string on focus.
 */
export function CurrencyInput({
  id,
  value,
  onChange,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
}: {
  id?: string;
  value: number | undefined;
  onChange: (n: number | undefined) => void;
  "aria-label"?: string;
  "aria-describedby"?: string;
}) {
  const [display, setDisplay] = useState(() =>
    value != null && value !== 0
      ? new Intl.NumberFormat("en-US").format(value)
      : ""
  );
  const [focused, setFocused] = useState(false);

  // Sync display when store value changes externally (e.g. reset)
  useEffect(() => {
    if (!focused) {
      setDisplay(
        value != null && value !== 0
          ? new Intl.NumberFormat("en-US").format(value)
          : ""
      );
    }
  }, [value, focused]);

  return (
    <AdornedInput
      id={id}
      type="text"
      inputMode="numeric"
      prefix="$"
      value={display}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      onFocus={() => {
        setFocused(true);
        setDisplay(value != null ? String(value) : "");
      }}
      onChange={(e) => {
        setDisplay(e.target.value);
        onChange(parseAmount(e.target.value));
      }}
      onBlur={(e) => {
        setFocused(false);
        const n = parseAmount(e.target.value);
        if (n !== undefined) {
          setDisplay(new Intl.NumberFormat("en-US").format(n));
          onChange(n);
        } else {
          setDisplay("");
          onChange(undefined);
        }
      }}
    />
  );
}

