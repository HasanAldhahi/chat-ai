import { describe, expect, it } from "vitest";
import {
  CHAT_AI_AGENTIC_OWNER,
  CHAT_AI_AGENT_ID_OPENHANDS,
  chatAiAgentTooltipI18nSuffix,
  isChatAiAgentModel,
} from "./chatAiAgentModels.js";

describe("isChatAiAgentModel (Task 3.2)", () => {
  it("returns true for agent catalog owned_by", () => {
    expect(
      isChatAiAgentModel({
        id: "X",
        owned_by: CHAT_AI_AGENTIC_OWNER,
      }),
    ).toBe(true);
  });

  it("returns true when id/name contains agent", () => {
    expect(isChatAiAgentModel({ id: "Agent - Foo" })).toBe(true);
    expect(isChatAiAgentModel({ name: "My Agent", id: "x" })).toBe(true);
  });

  it("returns false for normal chat model", () => {
    expect(isChatAiAgentModel({ id: "gpt-4", name: "GPT-4" })).toBe(false);
    expect(isChatAiAgentModel(null)).toBe(false);
  });
});

describe("chatAiAgentTooltipI18nSuffix (Task 4.5)", () => {
  it("maps bundled agent ids to suffix keys", () => {
    expect(
      chatAiAgentTooltipI18nSuffix({ id: CHAT_AI_AGENT_ID_OPENHANDS }),
    ).toBe("agent_openhands_tooltip");
  });

  it("falls back to agent_tooltip for unknown agent-like id", () => {
    expect(chatAiAgentTooltipI18nSuffix({ id: "Agent - Custom" })).toBe(
      "agent_tooltip",
    );
  });
});
