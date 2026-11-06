/** A failed API response: its HTTP status, the server's `detail` and a
 *  readable message. Callers branch on `status` (404 = gone, 409 = busy)
 *  instead of parsing the message.
 *
 *  Kept apart from api.ts so tests that mock the API module still get the
 *  real class for `instanceof` checks. */
export class ApiError extends Error {
  readonly status: number;
  /** FastAPI's `detail` when the body is JSON with one; else the raw body. */
  readonly detail: unknown;
  /** The server's explanation in words, without the status. */
  readonly detailText: string;

  constructor(status: number, body: string) {
    const detail = parseDetail(body);
    const text = describe(detail) || `Request failed`;
    super(`${text} (HTTP ${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.detailText = text;
  }
}

function parseDetail(body: string): unknown {
  try {
    const parsed = JSON.parse(body);
    return parsed && typeof parsed === "object" && "detail" in parsed ? parsed.detail : parsed;
  } catch {
    return body;
  }
}

/** FastAPI details are a string, an object with a message, or (422) a list
 *  of validation errors with `msg`. */
function describe(detail: unknown): string {
  if (typeof detail === "string") return detail.trim();
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : ""))
      .filter(Boolean)
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "";
}

export function isApiError(e: unknown, status?: number): e is ApiError {
  return e instanceof ApiError && (status === undefined || e.status === status);
}
