/**
 * Task 3.1: FastAPI broker proxy routes + shared helpers (testable).
 */
import fetch from "node-fetch";

/**
 * Map broker HTTP status for the browser (Task 3.4).
 * Upstream unavailable → 503; explicit gateway timeout → 504; other 5xx → 500.
 */
export function mapAgenticStatus(status) {
  if (status === 400 || status === 401 || status === 403 || status === 422) {
    return status;
  }
  if (status === 502 || status === 503) return 503;
  if (status === 504) return 504;
  if (status >= 500 && status < 600) return 500;
  return status >= 400 ? status : 200;
}

function brokerFetchSignal(timeoutMs) {
  const ms = Number(timeoutMs);
  if (!ms || ms < 1) return undefined;
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  return undefined;
}

/** Model label from chat-style request body (string or { name, id }). */
export function agentModelLabel(body) {
  const m = body?.model;
  if (typeof m === "string") return m;
  if (m && typeof m === "object") {
    return m.name || m.id || "";
  }
  return "";
}

/** True when request should use the agentic broker (Phase 3). */
export function isAgentModelRequestBody(body) {
  return String(agentModelLabel(body)).toLowerCase().includes("agent");
}

/**
 * Ensure broker `AgentChatRequest` fields: optional `user_id` defaults to X-User.
 * Other fields pass through; broker ignores extras (Pydantic `extra: ignore`).
 */
export function normalizeAgentChatPayload(body, xUser) {
  const base = body && typeof body === "object" ? { ...body } : {};
  if (!base.user_id && xUser) {
    base.user_id = xUser;
  }
  return base;
}

export function resolveXUser(req, env = process.env) {
  return (
    req.headers["x-user"] ||
    req.headers["X-User"] ||
    env.AGENTIC_DEFAULT_X_USER ||
    ""
  ).toString();
}

/**
 * POST /api/agent/chat → broker POST /api/agent/chat
 */
export async function proxyAgentChatPost(req, res, options) {
  const { brokerUrl, fetchImpl = fetch } = options;
  const xUser = resolveXUser(req);
  if (!xUser) {
    return res.status(401).json({
      error: "Authentication required. Please log in again.",
      code: "agentic_auth_required",
    });
  }
  const url = `${brokerUrl.replace(/\/$/, "")}/api/agent/chat`;
  const payload = normalizeAgentChatPayload(req.body, xUser);
  const timeoutMs =
    options.brokerTimeoutMs != null
      ? options.brokerTimeoutMs
      : Number(process.env.AGENTIC_BROKER_TIMEOUT_MS || 1_800_000);
  try {
    const brokerSignal = brokerFetchSignal(timeoutMs);
    const response = await fetchImpl(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User": xUser,
        ...(req.headers.authorization
          ? { Authorization: req.headers.authorization }
          : {}),
      },
      body: JSON.stringify(payload),
      ...(brokerSignal ? { signal: brokerSignal } : {}),
    });

    const ct = (response.headers.get("content-type") || "").toLowerCase();

    if (!response.ok) {
      let detailPayload = {};
      try {
        detailPayload = await response.json();
      } catch {
        /* ignore */
      }
      const detail = detailPayload.detail;
      const errMsg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? JSON.stringify(detail)
            : detailPayload.message ||
              response.statusText ||
              "agent chat error";
      const mapped = mapAgenticStatus(response.status);
      const bodyOut = { error: errMsg };
      if (detailPayload.code) bodyOut.code = detailPayload.code;
      return res.status(mapped).json(bodyOut);
    }

    if (ct.includes("text/event-stream") && response.body) {
      res.status(200);
      res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
      res.setHeader("Cache-Control", "no-cache, no-transform");
      res.setHeader("X-Accel-Buffering", "no");
      response.body.pipe(res);
      return;
    }

    const json = await response.json();
    return res.status(response.status).json(json);
  } catch (err) {
    (options.logger || console).error("POST agent chat proxy error:", err);
    const name = err && err.name;
    if (name === "AbortError" || name === "TimeoutError") {
      return res.status(504).json({
        error: "Agent session timed out after 30 minutes of inactivity",
        code: "agentic_timeout",
      });
    }
    return res.status(503).json({
      error:
        "Agent service temporarily unavailable. Please try again later.",
      code: "agentic_unavailable",
    });
  }
}

/**
 * GET /api/chat/agent/sse → broker GET /api/sse/{session_id}
 */
export async function proxyAgentSseGet(req, res, options) {
  const { brokerUrl, fetchImpl = fetch } = options;
  const sessionId = req.query.session_id;
  if (!sessionId || typeof sessionId !== "string") {
    return res.status(422).json({ error: "query session_id is required" });
  }
  const xUser = resolveXUser(req);
  if (!xUser) {
    return res.status(401).json({
      error: "Authentication required. Please log in again.",
      code: "agentic_auth_required",
    });
  }
  const url = `${brokerUrl.replace(/\/$/, "")}/api/sse/${encodeURIComponent(sessionId)}`;
  try {
    const response = await fetchImpl(url, {
      headers: {
        "X-User": xUser,
        Accept: "text/event-stream",
        ...(req.headers.authorization
          ? { Authorization: req.headers.authorization }
          : {}),
      },
    });
    if (!response.ok) {
      const txt = await response.text();
      let errBody = txt;
      try {
        const j = JSON.parse(txt);
        if (j && typeof j.error === "string") errBody = j.error;
        else if (j && j.detail != null) errBody = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* plain text */
      }
      return res
        .status(mapAgenticStatus(response.status))
        .json({ error: errBody });
    }
    res.status(200);
    res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache, no-transform");
    res.setHeader("X-Accel-Buffering", "no");
    if (response.body) {
      response.body.pipe(res);
    } else {
      res.end();
    }
  } catch (err) {
    (options.logger || console).error("GET agent SSE proxy error:", err);
    return res.status(503).json({
      error:
        "Agent service temporarily unavailable. Please try again later.",
      code: "agentic_unavailable",
    });
  }
}

/**
 * DELETE /api/agent/sessions/:session_id → broker DELETE /api/agent/sessions/{session_id}
 * Called by the front-end Stop button to cancel the running agent job.
 */
export async function proxyAgentSessionDelete(req, res, options) {
  const { brokerUrl, fetchImpl = fetch } = options;
  const sessionId = req.params.session_id;
  if (!sessionId) {
    return res.status(422).json({ error: "session_id param required" });
  }
  const xUser = resolveXUser(req);
  if (!xUser) {
    return res.status(401).json({
      error: "Authentication required. Please log in again.",
      code: "agentic_auth_required",
    });
  }
  const url = `${brokerUrl.replace(/\/$/, "")}/api/agent/sessions/${encodeURIComponent(sessionId)}`;
  try {
    const response = await fetchImpl(url, {
      method: "DELETE",
      headers: {
        "X-User": xUser,
        ...(req.headers.authorization
          ? { Authorization: req.headers.authorization }
          : {}),
      },
    });
    if (!response.ok) {
      let detail = {};
      try { detail = await response.json(); } catch { /* ignore */ }
      return res
        .status(mapAgenticStatus(response.status))
        .json({ error: detail.detail || detail.error || "cancel failed" });
    }
    const json = await response.json();
    return res.status(200).json(json);
  } catch (err) {
    (options.logger || console).error("DELETE agent session proxy error:", err);
    return res.status(503).json({
      error: "Agent service temporarily unavailable.",
      code: "agentic_unavailable",
    });
  }
}

/**
 * Proxy multipart file upload to broker POST /api/sessions/:session_id/files
 * Streams the raw body through so we don't buffer the whole file in Node.
 */
export async function proxySessionFileUpload(req, res, options) {
  const { brokerUrl, fetchImpl = fetch } = options;
  const { session_id } = req.params;
  const xUser = resolveXUser(req);
  const brokerTarget = `${brokerUrl}/api/sessions/${encodeURIComponent(session_id)}/files`;
  try {
    const response = await fetchImpl(brokerTarget, {
      method: "POST",
      headers: {
        ...req.headers,
        host: undefined,
        "x-user": xUser,
      },
      body: req,
      duplex: "half",
    });
    res.status(response.status);
    response.headers.forEach((v, k) => res.setHeader(k, v));
    response.body.pipe(res);
  } catch (err) {
    (options.logger || console).error("POST session file upload proxy error:", err);
    res.status(503).json({ error: "Agentic broker unavailable" });
  }
}

export function registerAgenticRoutes(app, options) {
  const opts = {
    fetchImpl: fetch,
    ...options,
    brokerUrl: (options.brokerUrl || "").replace(/\/$/, ""),
  };
  app.post("/api/chat/agent", (req, res) =>
    proxyAgentChatPost(req, res, opts),
  );
  app.get("/api/chat/agent/sse", (req, res) =>
    proxyAgentSseGet(req, res, opts),
  );
  app.delete("/api/agent/sessions/:session_id", (req, res) =>
    proxyAgentSessionDelete(req, res, opts),
  );
  app.post("/api/sessions/:session_id/files", (req, res) =>
    proxySessionFileUpload(req, res, opts),
  );
}
