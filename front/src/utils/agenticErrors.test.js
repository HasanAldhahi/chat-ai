import { describe, expect, it } from "vitest";
import { normalizeAgentHttpError } from "./agenticErrors.js";

describe("normalizeAgentHttpError (Task 3.4)", () => {
  it("maps 401 to login copy", () => {
    const r = normalizeAgentHttpError(401, "whatever");
    expect(r.display).toMatch(/log in again/i);
    expect(r.retryable).toBe(false);
    expect(r.status).toBe(401);
  });

  it("maps 403 to workspace access copy", () => {
    const r = normalizeAgentHttpError(403, "nope");
    expect(r.display).toContain("Access denied");
    expect(r.retryable).toBe(false);
  });

  it("maps 503 to service unavailable", () => {
    const r = normalizeAgentHttpError(503, "bad");
    expect(r.display).toMatch(/temporarily unavailable/i);
    expect(r.retryable).toBe(true);
  });

  it("maps 504 to inactivity timeout copy", () => {
    const r = normalizeAgentHttpError(504, "");
    expect(r.display).toMatch(/30 minutes/i);
    expect(r.retryable).toBe(true);
  });

  it("detects Slurm failure and job id", () => {
    const r = normalizeAgentHttpError(
      500,
      "Slurm job 12345678 failed on cluster",
    );
    expect(r.display).toContain("Slurm job 12345678");
    expect(r.retryable).toBe(true);
  });

  it("detects container / workspace start", () => {
    const r = normalizeAgentHttpError(
      502,
      "container failed to pull image",
    );
    expect(r.display).toMatch(/workspace failed to start/i);
    expect(r.retryable).toBe(true);
  });

  it("maps network / unknown status", () => {
    const r = normalizeAgentHttpError(undefined, "");
    expect(r.retryable).toBe(true);
    expect(r.status).toBe(0);
  });
});
