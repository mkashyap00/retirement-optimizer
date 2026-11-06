import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Format a timestamp string from the backend into a human-readable date+time.
 *
 * The backend returns timestamps as "YYYY-MM-DD HH:MM:SS.ffffff" (no timezone).
 * We normalise by replacing the space separator with "T" and trimming microseconds
 * to milliseconds so that `new Date()` parses the string reliably.  The value is
 * treated as **local time** (no "Z" suffix is appended).
 *
 * Also accepts standard ISO-8601 strings (e.g. "2026-01-15T10:00:00Z") unchanged.
 *
 * Returns "—" if input is empty, undefined, or malformed.
 *
 * Example: "2026-07-05 16:29:17.920023" → "Jul 5, 2026, 4:29 PM"
 */
export function formatDateTime(iso: string): string {
  if (!iso) return "—";

  // Replace space separator → "T", then trim any extra sub-millisecond digits
  const normalized = iso.replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(normalized);

  if (isNaN(d.getTime())) return "—";

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

export function calculateAge(birthDate: string): number {
  const today = new Date();
  const birth = new Date(birthDate);
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  
  return age;
}