/**
 * Browser client for Node GET /api/chat/agent/sse → broker session stream.
 * Parses SSE frames (event + data lines) per Task 1.6 / 3.3.
 */

export function resolveBackendBaseUrl() {
  let baseURL = import.meta.env.VITE_BACKEND_ENDPOINT;
  try {
    baseURL = new URL(baseURL).toString();
  } catch {
    baseURL = new URL(baseURL, window.location.origin).toString();
  }
  return baseURL;
}

export function resolveAgenticXUser() {
  return (
    import.meta.env.VITE_AGENTIC_X_USER ||
    import.meta.env.VITE_X_USER ||
    "dev@gwdg"
  );
}

function parseSseBlock(block) {
  let eventName = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n");
  let data = {};
  try {
    data = JSON.parse(payload);
  } catch {
    data = { message: payload };
  }
  return { event: eventName, data };
}

/** Exported for unit tests (Task 3.3 SSE parsing). */
export { parseSseBlock as parseAgentSseBlock };

/** @returns {boolean} */
function isCommentOnlyBlock(block) {
  const lines = block.split("\n").filter((l) => l.length > 0);
  return lines.length > 0 && lines.every((l) => l.startsWith(":"));
}

/**
 * Read fetch SSE body and invoke onFrame({ event, data }) per message.
 * Stops when stream ends or signal aborts.
 */
export async function readAgentSseBody(body, signal, onFrame) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!signal?.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const rawBlock = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!rawBlock.trim() || isCommentOnlyBlock(rawBlock)) continue;
        const frame = parseSseBlock(rawBlock);
        if (frame) onFrame(frame);
      }
    }
  } catch (err) {
    if (err?.name === "AbortError") return;
    throw err;
  } finally {
    reader.releaseLock?.();
  }
}

// One AbortController per session — prevents subscriber accumulation across messages.
const _sseControllers = new Map();

/**
 * Subscribe to broker tool/action SSE for an agent session.
 * Any previous SSE connection for the same sessionId is aborted first so only
 * one subscriber is active at a time (prevents duplicate frame delivery).
 * @returns {() => void} disposer that tears down this connection
 */
export function startAgentBrokerSse({
  sessionId,
  signal,
  onFrame,
  onConnectionError,
  onStreamEnd,
}) {
  if (!sessionId || !signal) return () => {};

  // Abort previous connection for this session (subscriber-leak fix).
  const prev = _sseControllers.get(sessionId);
  if (prev) {
    prev.abort();
    _sseControllers.delete(sessionId);
  }

  const controller = new AbortController();
  _sseControllers.set(sessionId, controller);

  // Chain to the caller's signal so the Stop button also kills the SSE.
  const onCallerAbort = () => controller.abort();
  signal.addEventListener("abort", onCallerAbort, { once: true });

  const run = async () => {
    try {
      const baseURL = resolveBackendBaseUrl();
      const url = new URL("api/chat/agent/sse", baseURL);
      url.searchParams.set("session_id", String(sessionId));
      const res = await fetch(url.toString(), {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          "X-User": resolveAgenticXUser(),
        },
        signal: controller.signal,
      });
      if (!res.ok) {
        onConnectionError?.(res.status);
        return;
      }
      if (!res.body) return;
      await readAgentSseBody(res.body, controller.signal, onFrame);
      // Stream closed normally — Goose process exited.
      if (!controller.signal.aborted) onStreamEnd?.();
    } catch (err) {
      if (err?.name === "AbortError") return;
      onConnectionError?.(err);
    } finally {
      signal.removeEventListener("abort", onCallerAbort);
      if (_sseControllers.get(sessionId) === controller) {
        _sseControllers.delete(sessionId);
      }
    }
  };

  void run();
  return () => controller.abort();
}

export function toolIconForType(type) {
  const t = String(type || "").toLowerCase();
  if (t.includes("web") || t === "web_search") return "🔍";
  if (t.includes("read") || t.includes("fs") || t === "fs_read") return "📄";
  if (t.includes("code") || t.includes("exec") || t === "code_exec") return "💻";
  return "⚙️";
}

const SSE_EVENTS = new Set([
  "action",
  "result",
  "error",
  "message",
  "assistant.delta",
  "assistant.final",
  "model.active",
]);

export function isAgentSseEventName(name) {
  return SSE_EVENTS.has(String(name || ""));
}

/**
 * Normalizes one SSE frame from the broker into a message row for React state.
 * For assistant.delta / assistant.final events, extracts the text chunk.
 */
export function normalizeAgentSseActivity(frame) {
  const { event, data } = frame;
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  const d = data && typeof data === "object" ? data : {};
  const timestamp = d.timestamp || d.time || new Date().toISOString();

  if (event === "assistant.delta" || event === "assistant.final") {
    return {
      id,
      sseEvent: event,
      type: event,
      timestamp,
      text: typeof d.text === "string" ? d.text : "",
      message: "",
      output: "",
      code: "",
      expanded: false,
    };
  }

  const type = d.type || d.tool || "";
  const msg = d.message ?? d.msg ?? "";
  const output = d.output ?? d.result ?? d.content ?? "";
  const code = d.code ?? d.status ?? "";
  const activity = {
    id,
    sseEvent: event,
    type: String(type),
    timestamp,
    message:
      typeof msg === "string" ? msg : msg != null ? JSON.stringify(msg) : "",
    output:
      output !== undefined && output !== null ? String(output) : "",
    code: code !== undefined && code !== null ? String(code) : "",
    expanded: false,
  };
  if (event === "error") {
    const detail = d.detail;
    activity.message =
      activity.message ||
      (typeof detail === "string"
        ? detail
        : detail != null
          ? JSON.stringify(detail)
          : JSON.stringify(d));
  }
  return activity;

}
