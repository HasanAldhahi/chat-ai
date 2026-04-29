/** Static agent catalog (Phase 3). `owned_by` marks rows for grouping in the model UI. */

export const CHAT_AI_AGENTIC_OWNER = "chat-ai-agentic";

/** Extended-model stubs so agents work in ModelSelectorExtended when that view is active. */
const extendedAgentStubs = {
  releaseDate: "—",
  company: "Chat AI",
  modelFamily: "Agent",
  contextLength: "—",
  numParameters: "—",
  description:
    "Tool-using agent (web, files, code) via the agentic broker. Cluster packaging varies by agent.",
  external: false,
};

export const CHAT_AI_AGENT_MODELS = [
  {
    id: "Agent - OpenHands (Web + Code + Files)",
    name: "🤖 Agent - OpenHands (Web + Code + Files)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
  },
  {
    id: "Agent - Goose (Fast reasoning)",
    name: "🤖 Agent - Goose (Fast reasoning)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
  },
  {
    id: "Agent - smolagents (Lightweight)",
    name: "🤖 Agent - smolagents (Lightweight)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
  },
  {
    id: "Agent - opencode (Code focus)",
    name: "🤖 Agent - opencode (Code focus)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
  },
];

export function isChatAiAgentModel(model) {
  if (!model) return false;
  if (model.owned_by === CHAT_AI_AGENTIC_OWNER) return true;
  const id = String(model.id ?? "").toLowerCase();
  const name = String(model.name ?? "").toLowerCase();
  return id.includes("agent") || name.includes("agent");
}
