import { describe, expect, it } from "vitest";
import {
  CHAT_AI_AGENTIC_OWNER,
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
