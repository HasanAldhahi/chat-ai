import { describe, expect, it, vi } from "vitest";
import {
  isAgentSseEventName,
  normalizeAgentSseActivity,
  parseAgentSseBlock,
  readAgentSseBody,
  toolIconForType,
} from "./agentBrokerSse.js";

describe("parseAgentSseBlock (Task 3.3)", () => {
  it("parses event + data JSON", () => {
    const block = ['event: action', 'data: {"type":"web_search","message":"hi"}'].join(
      "\n",
    );
    const f = parseAgentSseBlock(block);
    expect(f.event).toBe("action");
    expect(f.data.type).toBe("web_search");
    expect(f.data.message).toBe("hi");
  });

  it("joins multiple data: lines with newline", () => {
    const block = "data: hello\ndata: world";
    const f = parseAgentSseBlock(block);
    expect(f.data.message).toBe("hello\nworld");
  });

  it("returns null for comment-only", () => {
    expect(parseAgentSseBlock(": keepalive")).toBeNull();
  });
});

describe("readAgentSseBody", () => {
  it("emits frames from chunked stream", async () => {
    const chunks = [
      "event: result\n",
      'data: {"output":"x"}\n\n',
    ];
    const stream = new ReadableStream({
      start(controller) {
        const enc = new TextEncoder();
        for (const c of chunks) controller.enqueue(enc.encode(c));
        controller.close();
      },
    });
    const out = [];
    await readAgentSseBody(stream, {}, (f) => out.push(f));
    expect(out).toHaveLength(1);
    expect(out[0].event).toBe("result");
    expect(out[0].data.output).toBe("x");
  });
});

describe("toolIconForType (Task 3.3)", () => {
  it("maps known tools", () => {
    expect(toolIconForType("web_search")).toBe("🔍");
    expect(toolIconForType("fs_read")).toBe("📄");
    expect(toolIconForType("code_exec")).toBe("💻");
    expect(toolIconForType("other")).toBe("⚙️");
  });
});

describe("isAgentSseEventName", () => {
  it("accepts broker taxonomy", () => {
    expect(isAgentSseEventName("action")).toBe(true);
    expect(isAgentSseEventName("bogus")).toBe(false);
  });
});

describe("normalizeAgentSseActivity", () => {
  it("builds activity row", () => {
    vi.spyOn(Date, "now").mockReturnValue(1_700_000_000_000);
    vi.spyOn(Math, "random").mockReturnValue(0.123456789);
    const a = normalizeAgentSseActivity({
      event: "action",
      data: { type: "web_search", message: "Searching", timestamp: "t0" },
    });
    expect(a.sseEvent).toBe("action");
    expect(a.type).toBe("web_search");
    expect(a.message).toBe("Searching");
    expect(a.timestamp).toBe("t0");
    vi.restoreAllMocks();
  });
});
