import OpenAI from "openai";
import {
  resolveAgenticXUser,
  resolveBackendBaseUrl,
} from "../utils/agentBrokerSse";
import { isChatAiAgentModel } from "../constants/chatAiAgentModels";

// Controller for handling API request cancellation
let controller = new AbortController();

/** Same signal attached to in-flight agent/chat fetch — use for parallel SSE. */
export function getActiveRequestSignal() {
  return controller.signal;
}

function brokerMessages(messages) {
  return messages.map((m) => {
    let c = m.content;
    if (Array.isArray(c)) {
      c = c
        .filter((x) => x.type === "text")
        .map((x) => x.text || "")
        .join("\n");
    }
    return { role: m.role, content: c || "" };
  });
}

/**
 * Agent models: Node `/api/chat/agent` → FastAPI → vLLM (Tasks 3.1 + 2.6).
 * Retries transient browser network failures (Task 3.4).
 */
async function* agentChatCompletions(conversation, timeout = 30000, hooks = {}) {
  const baseURL = resolveBackendBaseUrl();
  const agentUrl = new URL("api/chat/agent", baseURL).toString();
  const model =
    typeof conversation.settings.model === "string"
      ? conversation.settings.model
      : conversation.settings.model?.name ||
        conversation.settings.model?.id ||
        "";

  const body = {
    model,
    messages: brokerMessages(conversation.messages || []),
    session_id: conversation.id || "",
    stream: true,
    temperature: conversation.settings.temperature ?? 0.5,
    top_p: conversation.settings.top_p ?? 0.5,
    ...(conversation.settings.goose_model?.id
      ? { llm_model: conversation.settings.goose_model.id }
      : {}),
  };

  const xUser = resolveAgenticXUser();

  const maxAttempts = 3;
  let res;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      res = await fetch(agentUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User": xUser,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      break;
    } catch (err) {
      if (err?.name === "AbortError") throw err;
      const transient =
        err instanceof TypeError ||
        (typeof err?.message === "string" &&
          /network|failed to fetch|load failed|networkerror|connection/i.test(
            err.message,
          ));
      if (!transient || attempt === maxAttempts) {
        const e = new Error(
          err?.message ||
            "Connection lost. Retrying failed — please try again.",
        );
        e.status = 0;
        throw e;
      }
      hooks.onAgentConnectionRetry?.(attempt);
      await new Promise((r) => setTimeout(r, 600 * attempt));
    }
  }

  // HTTP 202: runtime job submitted — response arrives over SSE, not in this stream.
  if (res.status === 202) {
    let json = {};
    try { json = await res.json(); } catch { /* ignore */ }
    yield { _agentAsync: true, job_id: json.job_id, session_id: json.session_id };
    return;
  }

  if (!res.ok) {
    let errObj = {};
    try {
      errObj = await res.json();
    } catch {
      /* ignore */
    }
    const e = new Error(errObj.error || res.statusText || "Agent chat failed");
    e.status = res.status;
    if (errObj.code) e.code = errObj.code;
    throw e;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of block.split("\n")) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        const payload = t.slice(5).trim();
        if (payload === "[DONE]") continue;
        try {
          const chunk = JSON.parse(payload);
          yield chunk;
        } catch {
          /* skip malformed */
        }
      }
    }
  }
}

async function* chatCompletions (
  conversation,
  timeout = 30000,
  stream = true,
  hooks = {},
) {
  try {
    const model = typeof conversation.settings.model === 'string'
      ? conversation.settings.model
      : conversation.settings.model?.id; // TODO fall back to defaultModel

    const modelLabel =
      typeof conversation.settings.model === "string"
        ? conversation.settings.model
        : conversation.settings.model?.name ||
          conversation.settings.model?.id ||
          "";

    if (isChatAiAgentModel(conversation.settings.model)) {
      yield* agentChatCompletions(conversation, timeout, hooks);
      return;
    }

    // Define base URL from config
    let baseURL = import.meta.env.VITE_BACKEND_ENDPOINT;
    try {
      // If absolute, parse directly
      baseURL = new URL(baseURL).toString();
    } catch {
      // If relative, resolve against current origin
      baseURL = new URL(baseURL, window.location.origin).toString();
    }
    
    
    // Initialize params
    const params = {
      model: model,
      messages: conversation.messages,
      temperature: conversation.settings.temperature,
      top_p: conversation.settings.top_p,
      stream: stream,
      stream_options: {include_usage: true },
    };

    // Handle tools
    if (conversation.settings?.enable_tools) {
      params.enable_tools = true;
      params.tools = conversation?.settings?.tools || [];
    }

    if (conversation.settings?.arcana && conversation.settings.arcana.id !== "") {
      params.arcana = conversation.settings.arcana;
    }

    if (conversation.settings?.feedback) {
      params.feedback = conversation.settings.feedback;
    }

    if (conversation.settings?.mcp_servers && conversation.settings.mcp_servers.length > 0) {
      params["mcp-servers"] = [conversation.settings.mcp_servers];
    }

    // Define openai object to call backend
    const openai = new OpenAI({
      baseURL : baseURL,
      apiKey: null,
      dangerouslyAllowBrowser: true,
      timeout: timeout
    });

    // Get chat completion response
    const streamResponse = await openai.chat.completions.create(
      params, { 
      signal: controller.signal,
    });

    if (!stream) {
      const result = streamResponse;
      console.log("Error:", result);
      return result;
    }

    let answer = ""
    let completed = false
    for await (const chunk of streamResponse) {
      //console.log(chunk);
      if (chunk?.object == "error") {
        console.log(chunk)
          const err = new Error(chunk?.message || "Unknown error");
          err.type = chunk?.type;
          err.status = chunk?.status || chunk?.code;
          err.code = chunk?.code || chunk?.status;
          throw err;
      }
      try {
        if (!completed) {
          answer += chunk.choices[0].delta?.content || ""
          // yield (chunk.choices[0].delta)
          yield chunk
        } else {
          yield chunk;
          return {
            answer, 
            usage: chunk?.usage || null
          };
        }
        if (chunk?.choices?.[0]?.finish_reason === 'stop') {
          completed = true
          // return answer
        }
      }
      catch (err) {
        console.log("Warning: ", err)
        console.log(chunk)
        // TODO forward exact error
        // res.status(response.status).send(response.statusText);
        // res.status(500).end();
      }
    }

    // // Handle auth error
    // if (response.status === 401) {
    //   //setShowModalSession(true);
    //   return 401;
    // }

    // // Handle request size error
    // if (response.status === 413) {
    //   // setShowBadRequest(true);
    //   return 413;
    // }

    // if (!response.ok) {
    //   throw new Error(response.statusText || "Error: " + response.status);
    // }

    // const reader = response.body.getReader();
    // const decoder = new TextDecoder();
    // let currentResponse = "";
    // let streamComplete = false;

    // try {
    //   // Stream and process response chunks
    //   while (!streamComplete) {
    //     const { value, done } = await reader.read();
    //     if (done) {
    //       streamComplete = true;
    //       break;
    //     }
    //     const decodedChunk = decoder.decode(value, { stream: true });
    //     yield decodedChunk
    //     currentResponse += decodedChunk;
    //   }
    //   return currentResponse;
    // } catch (error) {
    //   // Handle AbortError specifically during streaming
    //   if (error.name === "AbortError") {
    //     console.log("Request aborted by user")
    //     return currentResponse;
    //   }
    //   throw error;
    // }
  } catch (error) {
    // Handle AbortError at the top level
    if (error?.name === "AbortError") {
      return null;
    }
    throw error; // Propagate other errorsrs
  }
}

function abortRequest() {
  if (controller) {
    controller.abort(); // stops the stream/fetch
  }
  controller = new AbortController();
}

export { chatCompletions, abortRequest };
