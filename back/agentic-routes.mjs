/**
 * Task 3.1: FastAPI broker proxy routes + shared helpers (testable).
 */
import fetch from "node-fetch";

/** Map broker HTTP status to Node client response (502/503 → 500). */
export function mapAgenticStatus(status) {
  if (status === 400 || status === 401 || status === 403 || status === 422) {
    return status;
  }
  if (status === 502 || status === 503) return 500;
  return status >= 400 ? status : 200;
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
      error:
        "X-User header required for agent chat (or set AGENTIC_DEFAULT_X_USER for dev)",
    });
  }
  const url = `${brokerUrl.replace(/\/$/, "")}/api/agent/chat`;
  const payload = normalizeAgentChatPayload(req.body, xUser);
  try {
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
      return res.status(mapAgenticStatus(response.status)).json({ error: errMsg });
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
    return res.status(200).json(json);
  } catch (err) {
    (options.logger || console).error("POST agent chat proxy error:", err);
    return res.status(503).json({ error: "agentic broker unavailable" });
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
    return res.status(401).json({ error: "X-User header required" });
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
      return res
        .status(mapAgenticStatus(response.status))
        .json({ error: await response.text() });
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
    return res.status(503).json({ error: "agentic broker unavailable" });
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
}
