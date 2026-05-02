import assert from "node:assert";
import http from "http";
import { describe, test, before, after } from "node:test";

import express from "express";

import {
  agentModelLabel,
  isAgentModelRequestBody,
  mapAgenticStatus,
  normalizeAgentChatPayload,
  proxyAgentChatPost,
  proxyAgentSessionDelete,
  registerAgenticRoutes,
} from "../agentic-routes.mjs";

describe("agentic-routes helpers (Task 3.1)", () => {
  test("mapAgenticStatus preserves 4xx", () => {
    assert.strictEqual(mapAgenticStatus(400), 400);
    assert.strictEqual(mapAgenticStatus(401), 401);
    assert.strictEqual(mapAgenticStatus(403), 403);
    assert.strictEqual(mapAgenticStatus(422), 422);
  });

  test("mapAgenticStatus maps 502/503 to 503 (Task 3.4)", () => {
    assert.strictEqual(mapAgenticStatus(502), 503);
    assert.strictEqual(mapAgenticStatus(503), 503);
  });

  test("mapAgenticStatus preserves 504 and maps other 5xx to 500", () => {
    assert.strictEqual(mapAgenticStatus(504), 504);
    assert.strictEqual(mapAgenticStatus(500), 500);
  });

  test("mapAgenticStatus passes other errors", () => {
    assert.strictEqual(mapAgenticStatus(418), 418);
  });

  test("isAgentModelRequestBody detects agent label", () => {
    assert.strictEqual(isAgentModelRequestBody({ model: "Agent - OpenHands" }), true);
    assert.strictEqual(isAgentModelRequestBody({ model: { id: "Agent - Goose" } }), true);
    assert.strictEqual(isAgentModelRequestBody({ model: "gpt-4" }), false);
    assert.strictEqual(isAgentModelRequestBody({}), false);
  });

  test("agentModelLabel handles string and object", () => {
    assert.strictEqual(agentModelLabel({ model: "x" }), "x");
    assert.strictEqual(agentModelLabel({ model: { name: "n", id: "i" } }), "n");
    assert.strictEqual(agentModelLabel({ model: { id: "i" } }), "i");
  });

  test("normalizeAgentChatPayload sets user_id from X-User", () => {
    const p = normalizeAgentChatPayload(
      { model: "Agent - x", messages: [], stream: false },
      "a@b.c",
    );
    assert.strictEqual(p.user_id, "a@b.c");
    assert.strictEqual(p.model, "Agent - x");
  });

  test("normalizeAgentChatPayload keeps explicit user_id", () => {
    const p = normalizeAgentChatPayload(
      { user_id: "keep@me", model: "Agent - x", messages: [] },
      "other@x",
    );
    assert.strictEqual(p.user_id, "keep@me");
  });
});

describe("Task 3.1 broker proxy integration (mock broker)", () => {
  let broker;
  let brokerPort;
  let server;
  let port;

  before(() =>
    new Promise((resolve, reject) => {
      broker = http.createServer((req, res) => {
        const base = `http://127.0.0.1:${brokerPort}`;
        const u = new URL(req.url || "/", base);

        if (req.method === "POST" && u.pathname === "/api/agent/chat") {
          const chunks = [];
          req.on("data", (c) => chunks.push(c));
          req.on("end", () => {
            const raw = Buffer.concat(chunks).toString("utf8");
            let body = {};
            try {
              body = JSON.parse(raw || "{}");
            } catch {
              /* ignore */
            }
            const xu = req.headers["x-user"] || req.headers["X-User"];
            if (!xu) {
              res.writeHead(401, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ detail: "no user" }));
              return;
            }
            if (body.async202) {
              res.writeHead(202, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ job_id: "job-abc", session_id: body.session_id || "s1" }));
              return;
            }
            if (body.stream) {
              res.writeHead(200, {
                "Content-Type": "text/event-stream; charset=utf-8",
              });
              res.end("data: {\"ok\":1}\n\n");
              return;
            }
            if (body.bad === true) {
              res.writeHead(502, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ detail: "upstream" }));
              return;
            }
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(
              JSON.stringify({
                ok: true,
                got_user_id: body.user_id,
                got_model: body.model,
              }),
            );
          });
          return;
        }

        if (req.method === "DELETE" && u.pathname.startsWith("/api/agent/sessions/")) {
          const xu = req.headers["x-user"] || req.headers["X-User"];
          if (!xu) {
            res.writeHead(401, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: "auth" }));
            return;
          }
          const sid = u.pathname.replace("/api/agent/sessions/", "");
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ session_id: sid, cancelled: true }));
          return;
        }

        if (req.method === "GET" && u.pathname.startsWith("/api/sse/")) {
          const xu = req.headers["x-user"] || req.headers["X-User"];
          if (u.pathname.includes("forbid")) {
            res.writeHead(403, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: "nope" }));
            return;
          }
          if (!xu) {
            res.writeHead(401, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: "auth" }));
            return;
          }
          res.writeHead(200, {
            "Content-Type": "text/event-stream",
          });
          res.end(": ping\n\n");
          return;
        }

        res.writeHead(404);
        res.end();
      });
      broker.listen(0, "127.0.0.1", (err) => {
        if (err) return reject(err);
        brokerPort = broker.address().port;
        const app = express();
        app.use(express.json());
        app.post("/chat/completions", (req, res) => {
          if (isAgentModelRequestBody(req.body)) {
            return proxyAgentChatPost(req, res, {
              brokerUrl: `http://127.0.0.1:${brokerPort}`,
            });
          }
          return res.status(200).json({ legacy: true });
        });
        registerAgenticRoutes(app, {
          brokerUrl: `http://127.0.0.1:${brokerPort}`,
        });
        server = http.createServer(app);
        server.listen(0, "127.0.0.1", (e2) => {
          if (e2) return reject(e2);
          port = server.address().port;
          resolve();
        });
      });
    }),
  );

  after(() =>
    new Promise((resolve) => {
      server?.close(() => {
        broker?.close(() => resolve());
      });
    }),
  );

  test("POST /api/chat/agent forwards JSON, injects user_id, maps 502→503", async () => {
    const r1 = await fetch(`http://127.0.0.1:${port}/api/chat/agent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User": "u@test.org",
      },
      body: JSON.stringify({
        model: "Agent - OpenHands",
        messages: [{ role: "user", content: "hi" }],
        stream: false,
      }),
    });
    assert.strictEqual(r1.status, 200);
    const j1 = await r1.json();
    assert.strictEqual(j1.got_user_id, "u@test.org");
    assert.strictEqual(j1.got_model, "Agent - OpenHands");

    const r2 = await fetch(`http://127.0.0.1:${port}/api/chat/agent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User": "u@test.org",
      },
      body: JSON.stringify({
        model: "Agent - OpenHands",
        messages: [{ role: "user", content: "hi" }],
        stream: false,
        bad: true,
      }),
    });
    assert.strictEqual(r2.status, 503);
    const j2 = await r2.json();
    assert.ok(typeof j2.error === "string");
  });

  test("POST /api/chat/agent requires X-User", async () => {
    const r = await fetch(`http://127.0.0.1:${port}/api/chat/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "Agent - OpenHands",
        messages: [{ role: "user", content: "hi" }],
      }),
    });
    assert.strictEqual(r.status, 401);
  });

  test("POST /api/chat/agent streams SSE from broker", async () => {
    const r = await fetch(`http://127.0.0.1:${port}/api/chat/agent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User": "u@s",
      },
      body: JSON.stringify({
        model: "Agent - OpenHands",
        messages: [{ role: "user", content: "hi" }],
        stream: true,
      }),
    });
    assert.strictEqual(r.status, 200);
    const ct = r.headers.get("content-type") || "";
    assert.ok(ct.includes("text/event-stream"));
    const text = await r.text();
    assert.ok(text.includes("data:"));
  });

  test("GET /api/chat/agent/sse proxies and maps 403", async () => {
    const ok = await fetch(
      `http://127.0.0.1:${port}/api/chat/agent/sse?session_id=s1`,
      { headers: { "X-User": "u@s" } },
    );
    assert.strictEqual(ok.status, 200);

    const forbidden = await fetch(
      `http://127.0.0.1:${port}/api/chat/agent/sse?session_id=forbid`,
      { headers: { "X-User": "u@s" } },
    );
    assert.strictEqual(forbidden.status, 403);
  });

  test("GET /api/chat/agent/sse requires session_id", async () => {
    const r = await fetch(`http://127.0.0.1:${port}/api/chat/agent/sse`, {
      headers: { "X-User": "u@s" },
    });
    assert.strictEqual(r.status, 422);
  });

  test("POST /chat/completions with agent model forwards to broker (Task 3.1)", async () => {
    const r = await fetch(`http://127.0.0.1:${port}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User": "agentpath@test",
      },
      body: JSON.stringify({
        model: "Agent - OpenHands",
        messages: [{ role: "user", content: "x" }],
        stream: false,
      }),
    });
    assert.strictEqual(r.status, 200);
    const j = await r.json();
    assert.strictEqual(j.got_user_id, "agentpath@test");
  });

  test("POST /api/chat/agent passes broker 202 through to client (Task 6.5)", async () => {
    const r = await fetch(`http://127.0.0.1:${port}/api/chat/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-User": "u@gwdg" },
      body: JSON.stringify({
        model: "Agent - Goose",
        messages: [{ role: "user", content: "hi" }],
        stream: false,
        async202: true,
        session_id: "mysession",
      }),
    });
    assert.strictEqual(r.status, 202);
    const j = await r.json();
    assert.strictEqual(j.job_id, "job-abc");
    assert.strictEqual(j.session_id, "mysession");
  });

  test("DELETE /api/agent/sessions/:id proxies session cancel (Task 6.5)", async () => {
    const r = await fetch(
      `http://127.0.0.1:${port}/api/agent/sessions/sess-xyz`,
      { method: "DELETE", headers: { "X-User": "u@gwdg" } },
    );
    assert.strictEqual(r.status, 200);
    const j = await r.json();
    assert.strictEqual(j.session_id, "sess-xyz");
    assert.strictEqual(j.cancelled, true);
  });

  test("DELETE /api/agent/sessions/:id requires X-User (Task 6.5)", async () => {
    const r = await fetch(
      `http://127.0.0.1:${port}/api/agent/sessions/sess-xyz`,
      { method: "DELETE" },
    );
    assert.strictEqual(r.status, 401);
  });
});
