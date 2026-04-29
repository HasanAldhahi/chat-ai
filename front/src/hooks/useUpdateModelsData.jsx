// useUpdateModelsData.js
import { useState, useEffect, useCallback } from "react";
import { getModelsData } from "../apis/getModelsData";
import { useToast } from "./useToast";
import { useModal } from "../modals/ModalContext";

/** Static agent entries (Task 3.2). Task 4.2 smolagents intentionally omitted. */
const CHAT_AI_AGENT_MODELS = [
  {
    id: "Agent - OpenHands (Web + Code + Files)",
    name: "🤖 Agent - OpenHands (Web + Code + Files)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: "chat-ai-agentic",
    demand: 0,
    status: "ready",
    created: 0,
  },
  {
    id: "Agent - Goose (Fast reasoning)",
    name: "🤖 Agent - Goose (Fast reasoning)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: "chat-ai-agentic",
    demand: 0,
    status: "ready",
    created: 0,
  },
  {
    id: "Agent - opencode (Code focus)",
    name: "🤖 Agent - opencode (Code focus)",
    object: "model",
    input: ["text"],
    output: ["text"],
    owned_by: "chat-ai-agentic",
    demand: 0,
    status: "ready",
    created: 0,
  },
];

export function useUpdateModelsData() {
  const [modelsData, setModelsData] = useState([]);
  const { notifyError } = useToast();
  const { openModal } = useModal();

  const updateModelsData = useCallback(async () => {
    try {
      const data = await getModelsData();

      if (data instanceof Response) {
        if (data.status === 401) openModal("errorSessionExpired");
        else notifyError(`Failed to fetch models: ${data.status} ${data.statusText}`);
        return;
      }

      if (Array.isArray(data) && data.length === 0) {
        notifyError("No models available or network error");
        return;
      }
      setModelsData([...CHAT_AI_AGENT_MODELS, ...data]);
    } catch {
      notifyError("Error fetching models");
    }
  }, []);

  useEffect(() => {
    updateModelsData();
    const interval = setInterval(updateModelsData, 30000);
    return () => clearInterval(interval);
  }, [updateModelsData]);

  return modelsData;
}