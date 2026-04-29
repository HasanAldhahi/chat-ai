/** Static agent catalog (Phase 3). `owned_by` marks rows for grouping in the model UI. */

export const CHAT_AI_AGENTIC_OWNER = "chat-ai-agentic";

/** Model `id` strings — stable for routing and i18n lookup (Task 4.5). */
export const CHAT_AI_AGENT_ID_OPENHANDS = "Agent - OpenHands (Web + Code + Files)";
export const CHAT_AI_AGENT_ID_GOOSE = "Agent - Goose (Fast reasoning)";
export const CHAT_AI_AGENT_ID_SMOLAGENTS = "Agent - smolagents (Lightweight)";
export const CHAT_AI_AGENT_ID_OPENCODE = "Agent - opencode (Code focus)";

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

/** i18n keys under `model_selector.*` for Tooltip copy (Task 4.5). */
export const CHAT_AI_AGENT_TOOLTIP_I18N_KEYS = {
  [CHAT_AI_AGENT_ID_OPENHANDS]: "agent_openhands_tooltip",
  [CHAT_AI_AGENT_ID_GOOSE]: "agent_goose_tooltip",
  [CHAT_AI_AGENT_ID_SMOLAGENTS]: "agent_smolagents_tooltip",
  [CHAT_AI_AGENT_ID_OPENCODE]: "agent_opencode_tooltip",
};

/**
 * Key for react-i18next `t(\`model_selector.${key}\`)`.
 * Falls back to generic `agent_tooltip` for unknown agent-shaped models.
 */
export function chatAiAgentTooltipI18nSuffix(model) {
  if (!model?.id) return "agent_tooltip";
  return CHAT_AI_AGENT_TOOLTIP_I18N_KEYS[String(model.id)] ?? "agent_tooltip";
}

export const CHAT_AI_AGENT_MODELS = [
  {
    id: CHAT_AI_AGENT_ID_OPENHANDS,
    name: "🤖 Agent - OpenHands (Web + Code + Files)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
    description:
      "Default agent: OpenHands with MCP tools (filesystem, web, code) on the cluster.",
  },
  {
    id: CHAT_AI_AGENT_ID_GOOSE,
    name: "🤖 Agent - Goose (Fast reasoning)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
    description:
      "Goose CLI with MCP and broker routing — tuned for fast multi-step reasoning.",
  },
  {
    id: CHAT_AI_AGENT_ID_SMOLAGENTS,
    name: "🤖 Agent - smolagents (Lightweight)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
    description:
      "Lightweight Hugging Face agents profile (cluster image follows repo packaging).",
  },
  {
    id: CHAT_AI_AGENT_ID_OPENCODE,
    name: "🤖 Agent - opencode (Code focus)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: CHAT_AI_AGENTIC_OWNER,
    demand: 0,
    status: "ready",
    created: 0,
    ...extendedAgentStubs,
    description:
      "OpenCode (sst/opencode) terminal agent with MCP stdio bridge — strong code focus.",
  },
];

export function isChatAiAgentModel(model) {
  if (!model) return false;
  if (model.owned_by === CHAT_AI_AGENTIC_OWNER) return true;
  const id = String(model.id ?? "").toLowerCase();
  const name = String(model.name ?? "").toLowerCase();
  return id.includes("agent") || name.includes("agent");
}
