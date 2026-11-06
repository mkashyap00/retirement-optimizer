/**
 * Unit tests for formatDateTime in src/lib/utils.ts
 */

import { formatDateTime } from "../utils";

// The backend timestamp "2026-07-05 16:29:17.920023" has no timezone specifier
// so it is treated as local time and formatted in the local timezone.
// This test runs in a UTC environment but the local→local identity holds in any zone.

describe("formatDateTime", () => {
  it("formats a backend microsecond timestamp correctly", () => {
    const result = formatDateTime("2026-07-05 16:29:17.920023");
    expect(result).toContain("Jul 5, 2026");
    expect(result).toContain("4:29");
  });

  it("includes 'PM' for an afternoon time", () => {
    const result = formatDateTime("2026-07-05 16:29:17.920023");
    expect(result).toContain("PM");
  });

  it("also accepts a standard ISO-8601 string with T separator", () => {
    // Z-suffixed strings are UTC-anchored and shift by local timezone.
    // Verify it returns a formatted string (not "—") and contains the year.
    const result = formatDateTime("2026-01-15T10:00:00Z");
    expect(result).not.toEqual("—");
    expect(result).toContain("2026");
  });

  it("returns a non-empty string for a midnight timestamp", () => {
    const result = formatDateTime("2026-07-01 00:00:00.000000");
    expect(result.length).toBeGreaterThan(0);
    expect(result).toContain("Jul 1, 2026");
  });

  it("returns '—' for an empty string", () => {
    const result = formatDateTime("");
    expect(result).toEqual("—");
  });

  it("returns '—' for malformed input", () => {
    const result = formatDateTime("garbage");
    expect(result).toEqual("—");
  });

  it("returns '—' for undefined input", () => {
    const result = formatDateTime(undefined as unknown as string);
    expect(result).toEqual("—");
  });
});
