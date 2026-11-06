import { ApiError, isApiError } from "@/lib/apiError";

describe("ApiError", () => {
  it("reads FastAPI's string detail", () => {
    const e = new ApiError(404, '{"detail":"Household not found"}');
    expect(e.status).toBe(404);
    expect(e.detail).toBe("Household not found");
    expect(e.detailText).toBe("Household not found");
    expect(e.message).toBe("Household not found (HTTP 404)");
  });

  it("keeps a structured detail for recovery code", () => {
    const e = new ApiError(409, '{"detail":{"message":"busy","job_id":"j1"}}');
    expect(e.detail).toEqual({ message: "busy", job_id: "j1" });
    expect(e.detailText).toBe("busy");
    expect(isApiError(e, 409)).toBe(true);
    expect(isApiError(e, 404)).toBe(false);
  });

  it("joins validation errors", () => {
    const e = new ApiError(422, '{"detail":[{"msg":"too young"},{"msg":"too old"}]}');
    expect(e.detailText).toBe("too young; too old");
  });

  it("falls back to the raw body, then to a generic message", () => {
    expect(new ApiError(502, "Bad gateway").message).toBe("Bad gateway (HTTP 502)");
    expect(new ApiError(500, "").message).toBe("Request failed (HTTP 500)");
  });

  it("is not confused with an ordinary error", () => {
    expect(isApiError(new Error("HTTP 404: gone"))).toBe(false);
  });
});
