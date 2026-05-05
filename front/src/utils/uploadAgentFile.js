/**
 * Upload a File to the agentic session workspace.
 * Returns { path, name, size } on success — path is the in-container path (/workspace/filename).
 */
import { resolveBackendBaseUrl, resolveAgenticXUser } from "./agentBrokerSse";

export async function uploadAgentFile(sessionId, file) {
  if (!sessionId) throw new Error("No active session — send a message to Goose first.");

  const baseURL = resolveBackendBaseUrl();
  const url = new URL(`api/sessions/${encodeURIComponent(sessionId)}/files`, baseURL).toString();

  const form = new FormData();
  form.append("file", file, file.name);

  const res = await fetch(url, {
    method: "POST",
    headers: { "X-User": resolveAgenticXUser() },
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }

  return res.json(); // { path, name, size }
}
