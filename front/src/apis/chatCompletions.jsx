import OpenAI from "openai";

// Controller for handling API request cancellation
let controller = new AbortController();

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
 */
async function* agentChatCompletions(conversation, timeout = 30000) {
  let baseURL = import.meta.env.VITE_BACKEND_ENDPOINT;
  try {
    baseURL = new URL(baseURL).toString();
  } catch {
    baseURL = new URL(baseURL, window.location.origin).toString();
  }
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
  };

  const xUser =
    import.meta.env.VITE_AGENTIC_X_USER ||
    import.meta.env.VITE_X_USER ||
    "dev@gwdg";

  const res = await fetch(agentUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User": xUser,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  });

  if (!res.ok) {
    let errObj = {};
    try {
      errObj = await res.json();
    } catch {
      /* ignore */
    }
    const e = new Error(errObj.error || res.statusText || "Agent chat failed");
    e.status = res.status;
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

    if (String(modelLabel).toLowerCase().includes("agent")) {
      yield* agentChatCompletions(conversation, timeout);
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
