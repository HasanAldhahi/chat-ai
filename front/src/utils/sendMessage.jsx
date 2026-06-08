/* eslint-disable no-unused-vars */
import OpenAI from "openai";
import { useSelector } from "react-redux";
import { editMemory, addMemory, selectAllMemories } from "../Redux/reducers/userSettingsReducer";
import {
  chatCompletions,
  getActiveRequestSignal,
} from "../apis/chatCompletions";
import { isChatAiAgentModel } from "../constants/chatAiAgentModels";
import {
  isAgentSseEventName,
  normalizeAgentSseActivity,
  startAgentBrokerSse,
} from "../utils/agentBrokerSse";
import { normalizeAgentHttpError } from "../utils/agenticErrors";
import generateMemory from "../apis/generateMemory";
import generateChoiceProposal from "../apis/generateChoiceProposal";
import generateTitle from "../apis/generateTitle";
import { loadFile, loadFileMeta, saveFile, updateConversation, updateConversationMeta } from "../db";
import { getFileType, readFileAsBase64, readFileAsText } from "./attachments";
import { processFile } from "../apis/processFile";
import { uploadAgentFile } from "./uploadAgentFile";

// Text to be appended to system prompt for memories
const memoryExplanation = "The following list of memories was gathered by the system from previous conversations and may be irrelevant now. You may refer to relevant items only if justified to provide a more personalized and contextual response. Do not make any assumptions based on memories, instead focus on the user messages and requests:"

// Convert content items to standard OpenAI API
export async function processContentItems({
  items,
  ignoreImages = false, 
  ignoreAudio = false, 
  ignoreVideo = false, 
  ignoreDocs = false,
  convertDocs = true,
}) {
  const output = [];
  for (const item of items) {
    if (item.type === 'text') {
      if (item.text && items.length === 1) {
        return item.text
      }
      output.push(item)
      continue;
    }

    if (item.type === 'file' && item.fileId) {
      const meta = await loadFileMeta(item.fileId);
      if (!meta) {
        console.warn(`File meta not found for fileId=${item.fileId}`);
        continue;
      }
      const mimeType = meta.type.toLowerCase();
      const fileType = getFileType(meta);
      // Skip unsupported files
      if (ignoreImages && fileType === "image") continue;
      else if (ignoreAudio && fileType === "audio") continue;
      else if (ignoreVideo && fileType === "video") continue;
      else if (ignoreDocs
        && fileType !== "image"
        && fileType !== "audio"
        && fileType !== "video")
        continue;
      // Load supported files
      const file = await loadFile(item.fileId);
      if (!file) {
        console.warn(`File data not found for fileId=${item.fileId}`);
        continue;
      }
      
      // Handle based on generic file type
      if (fileType === "image") {
        // Send as Base64 data URL for image
        const dataUrl = await readFileAsBase64(file);
        output.push({
          type: "image_url",
          image_url: { url: dataUrl }
        });
      }
      else if (fileType === "video") {
        // Send as Base64 data URL for video
        const dataUrl = await readFileAsBase64(file);
        output.push({
          type: "video_url",
          video_url: { url: dataUrl }
        });
      }
      else if (fileType === "audio") {
        // Base64 encoding without data prefix for audio
        const base64Data = await readFileAsBase64(file);
        // Determine audio format from MIME type
        let format = 'mp3';
        if (mimeType.includes('wav')) {
          format = 'wav';
        }
        output.push({
          type: "input_audio",
          input_audio: {
            data: base64Data.split(",")[1], // Remove prefix
            format
          }
        });
      }
      else if (convertDocs) {
        if (fileType === "pdf" || fileType === "excel" || fileType === "docx") {
          // Convert binary document to markdown via /documents endpoint
          try {
            const result = await processFile(file);
            if (result.success && result.content) {
              output.push({ type: "text", text: result.content });
            } else {
              console.warn(`Failed to process document ${meta.name}: ${result.error}`);
            }
          } catch (error) {
            console.warn(`Error processing document ${meta.name}: ${error}`);
          }
          continue;
        }
        // Try to add file as text
        try {
          const textContent = await readFileAsText(file);
          output.push({
            type: "text",
            text: textContent
          });
        } catch (error) {
          console.warn(`Unsupported file type: ${mimeType}, ${error}`);
        }
      } else {
          // Try to add file in OpenAI format
          try {
            const base64Data = await readFileAsBase64(file);
            output.push({
              type: "file",
              file: {
                file_data: base64Data,
                filename: file.name,
              }
            });
          } catch (error) {
            console.warn(`Unsupported file type: ${mimeType}, ${error}`);
          }
      }
    }
  }
  if (output.length == 1 && typeof output[0]?.text === "string")
    return output[0].text;
  return output;
}

function receiveFile(base64Data, mimeType, filename = null, conversationId = null, ext = null) {
  // Decode base64 data
  const byteCharacters = atob(base64Data);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);

  // Create File object
  let file;

  if (filename) {
    file = new File([byteArray], filename, { type: mimeType });
  }
  else if (ext) {
    file = new File([byteArray], "file." + ext, { type: mimeType });
  } else {
    file = new File([byteArray], "file." + mimeType.split("/")[1], { type: mimeType });
  }

  // Save file
  // TODO replace id with conversation id
  const fileId = saveFile(conversationId, file);
  return fileId;
}

// Build OpenAI standard conversation from localState
async function buildConversationForAPI(localState) {
  // Determine supported file types from model
  const model = localState.settings.model;
  const ignoreAudio = !(localState.settings.enable_tools || (model?.input?.includes("audio") || false));
  const ignoreVideo = !(localState.settings.enable_tools || (model?.input?.includes("video") || false));
  const ignoreImages = !(localState.settings.enable_tools || (model?.input?.includes("image") || false));
  // Convert to API standard, ignore unsupported files and system message
  const processedMessages = await Promise.all(
    localState.messages.map(async (message) => {
      if (Array.isArray(message.content)) {
        return {
          role: message.role,
          content: await processContentItems({
            items: message.content,
            ignoreImages,
            ignoreAudio,
            ignoreVideo,
        })
        };
      }
      return message;
    })
  );
  // Return full standard conversation
  return {
    ...localState,
    messages: processedMessages,
    settings: {...localState.settings},
  };
}

const sendMessage = async ({
  localState,
  setLocalState,
  memories,
  openModal,
  notifyError,
  notifySuccess,
  dispatch,
  timeout,
  t = (key) => key,
}) => {
  const conversationId = localState.id

  try {
    const isArcanaSupported = localState.settings.model?.input?.includes("arcana") || (localState.settings?.enable_tools && !!localState.settings.tools.arcana)   

    const feedbackModule = import.meta.env.VITE_MODULE_FEEDBACK === "true";
    const toolsModule = import.meta.env.VITE_MODULE_TOOLS === "true";
    const choicesModule = import.meta.env.VITE_MODULE_CHOICES === "true";

    let finalConversationForState; // For local state updates
    let conversationForAPI = await buildConversationForAPI(localState);
    // Prepare system prompt
    let systemPromptAPI = localState.messages[0].role == "system"
      ? localState.messages[0].content[0].text
      : "";
    if (localState.settings?.memory != 0 && memories.length > 0) {
      const memoryContext = memories.map((memory) => memory.text).join("\n");
      const memorySection = `\n\n--- Begin User Memory ---\n${memoryExplanation}\n\n${memoryContext}\n--- End User Memory ---`;
      systemPromptAPI = systemPromptAPI + memorySection;
    }
    
    // Handle tools
    if (toolsModule && conversationForAPI.settings?.enable_tools) {
      // Inject the current date and time to the system prompt in human-readable format
      const currentDate = new Date().toLocaleString();
      systemPromptAPI = `\n\n--- Begin System Context ---\nCurrent Date: ${currentDate}\n--- End System Context ---` + systemPromptAPI;
      // Convert tools dictionary to OpenAI-compatible tools list
      conversationForAPI.settings.tools = Object.entries(localState.settings.tools)
                .filter(([_, enabled]) => enabled)
                .map(([toolKey]) => ({ type: toolKey }));
      if (conversationForAPI.settings?.arcana?.id && conversationForAPI.settings.arcana.id !== "") {
        conversationForAPI.settings.arcana.limit = 3;
      }
      // Always inject audio_transcription tool for now
      conversationForAPI.settings.tools.push({ type: "audio_transcription" });
    } else {
      delete conversationForAPI.settings.tools;
    }

    // Remove MCP and arcana if not enabled
    if (!localState.settings?.enable_tools || !localState.settings.tools.mcp) delete conversationForAPI.settings.mcp_servers;
    if (!localState.settings?.enable_tools || !localState.settings.tools.arcana) delete conversationForAPI.settings.arcana;
      
    // Clean conversation for API call
    conversationForAPI = {
      ...conversationForAPI,
      messages: conversationForAPI.messages.filter(
        (message) => 
        message.role === "user"
        || message.role === "assistant"
      ),
    };

    // Set system prompt in conversationForAPI
    if (systemPromptAPI) {
      conversationForAPI = {
        ...conversationForAPI,
        messages: [{
          role: "system",
          content: systemPromptAPI, // content is string here
        },
        ...conversationForAPI.messages,
      ]}
    }

    // Ensure timeout value is within valid range
    const timeoutAPI = (timeout >= 5000 && timeout <= 900000) ? timeout : 300000;
    
    if(feedbackModule){
      // add Feedback information
      if (conversationForAPI.settings?.tools == undefined){
        conversationForAPI.settings.tools = {
            enabled: true
          }
      } else{
        conversationForAPI.settings.tools.enabled = true;
      }
      let message = localState.messages[localState.messages.length - 1];
      if (Array.isArray(message.content)) {
        if (message?.feedback){
            conversationForAPI.settings.feedback = message.feedback;
        }
      }
    }
    
    const agentHooks = {
      onAgentConnectionRetry: () => {
        notifySuccess(t("agentic.retrying_connection"));
      },
    };

    if(!setLocalState){   
      // console.log(conversationForAPI);
      // send the message WITHOUT changing the UI with any response
      // TODO handle errors and print them to the user
      for await (const chunk of chatCompletions(conversationForAPI, timeoutAPI, true, agentHooks)){
        console.log(chunk);
      }
      return;
    }
    const _isAgentTurn = isChatAiAgentModel(localState.settings.model);
    // Pushing message into conversation history
    setLocalState((prev) => {
      // Clear any stale loading states from previous in-flight requests so they
      // don't stay stuck when the user sends a new message before the last one
      // resolves (the old async202Promise will never resolve once its SSE is aborted).
      const clearedMessages = prev.messages.map((msg) =>
        msg.role === "assistant" && msg.loading ? { ...msg, loading: false } : msg
      );
      return {
        ...prev,
        messages: [
          ...clearedMessages,
          {
            role: "assistant",
            content: [{ type: "text", text: ""}],
            loading: true,
            // Mark agent messages so GooseTerminalRenderer is used from the start
            ...(_isAgentTurn ? { agentActivities: [] } : {}),
          },
          { role: "user", content: [{ type: "text", text: "" }] },
        ],
        hasFirstPrompt: true,
        flush: true,
      };
    });

    // Stream assistant response into localState
    async function getChatChunk(conversationId, messageId = null) {
      const modelForAgent = localState.settings.model;
      let currentContent = [{"type": "text", "text": ""}];

      // For async-202 agent sessions, resolve this promise when SSE signals completion.
      let resolveAsync202 = null;
      const async202Promise = new Promise((resolve) => { resolveAsync202 = resolve; });
      // Once resolved, gate further onFrame updates so parallel Goose jobs
      // don't re-set loading=true or overwrite the finished bubble.
      let agentResolved = false;
      let disposeSSE = null;

      const resolveAgent = (payload) => {
        if (agentResolved) return;
        agentResolved = true;
        // Session over — any model still marked "running" has finished now.
        setLocalState((prev) => {
          if (prev.id !== conversationId) return prev;
          const messages = [...prev.messages];
          const idx = messages.length - 2;
          const row = messages[idx];
          if (!row || row.role !== "assistant" || !row.agentModels?.length) return prev;
          const list = row.agentModels.map((m) =>
            m.status === "running" ? { ...m, status: "done" } : m,
          );
          messages[idx] = { ...row, agentModels: list };
          return { ...prev, messages, ignoreConflict: true };
        });
        resolveAsync202?.(payload);
        // Close SSE so events from parallel Goose jobs stop arriving.
        disposeSSE?.();
      };

      if (isChatAiAgentModel(modelForAgent) && conversationId) {
        disposeSSE = startAgentBrokerSse({
          sessionId: conversationId,
          signal: getActiveRequestSignal(),
          onStreamEnd: () => {
            // Goose process exited — SSE stream closed. Finalize the bubble now
            // so all message events that arrived before stream-end are visible.
            resolveAgent({ answer: currentContent, usage: null });
          },
          onFrame: (frame) => {
            if (!isAgentSseEventName(frame.event)) return;

            // model.active: an LLM model started or finished handling the request.
            // We keep a running list so the UI can show every model that has been
            // active (orchestrator + each delegated specialist) with live status.
            if (frame.event === "model.active") {
              const model = frame.data?.model || "";
              const capability = frame.data?.capability || "orchestrator";
              const phase = frame.data?.phase || "start";
              const task = frame.data?.task || "";
              const error = frame.data?.error || "";
              setLocalState((prev) => {
                if (prev.id !== conversationId) return prev;
                const messages = [...prev.messages];
                const idx = messages.length - 2;
                const row = messages[idx];
                if (!row || row.role !== "assistant") return prev;
                const list = [...(row.agentModels || [])];
                // Match on capability+model so re-runs of the same specialist update
                // the existing chip instead of stacking duplicates.
                const key = `${capability}:${model}`;
                const at = list.findIndex((m) => m.key === key);
                const next = {
                  key,
                  model,
                  capability,
                  status: phase === "end" ? "done" : "running",
                  ...(task ? { task } : {}),
                  ...(error ? { error } : {}),
                };
                if (at >= 0) list[at] = { ...list[at], ...next };
                else list.push(next);
                messages[idx] = { ...row, agentModels: list };
                return { ...prev, messages, ignoreConflict: true };
              });
              return;
            }

            // message: goose stdout line → append to bubble text, no activity row
            if (frame.event === "message") {
              if (agentResolved) return; // response already finalised
              const raw = frame.data?.text || "";
              // Filter out goose ASCII art / session banner / prompt-echo lines
              const isHeader = /^[\s_\\/<>()\|L*●·\-]+$/.test(raw)
                || raw.includes("goose is ready")
                || raw.includes("new session")
                || /^\s*\w+\)\s+\d{8}_\d+/.test(raw)   // "____) 20260501_4 · /workspace"
                || /^\s*\(\s*[A-Z]\s*\)\s*>/.test(raw) // "( G )> " interactive prompt
                || /^\s*$/.test(raw);                   // blank lines
              if (raw && !isHeader) {
                currentContent[0].text += raw + "\n";
                setLocalState((prev) => {
                  if (prev.id !== conversationId) return prev;
                  const messages = [...prev.messages];
                  const idx = messages.length - 2;
                  const row = messages[idx];
                  if (!row || row.role !== "assistant") return prev;
                  messages[idx] = { ...row, content: currentContent, loading: true };
                  return { ...prev, messages, ignoreConflict: true };
                });
              }
              return; // never add message events as activity rows
            }

            // assistant.delta: stream partial text into bubble
            if (frame.event === "assistant.delta") {
              if (agentResolved) return;
              const chunk = frame.data?.text || "";
              if (chunk) {
                currentContent[0].text += chunk;
                setLocalState((prev) => {
                  if (prev.id !== conversationId) return prev;
                  const messages = [...prev.messages];
                  const idx = messages.length - 2;
                  const row = messages[idx];
                  if (!row || row.role !== "assistant") return prev;
                  messages[idx] = { ...row, content: currentContent, loading: true };
                  return { ...prev, messages, ignoreConflict: true };
                });
              }
              return;
            }

            // assistant.final: set final text + resolve
            if (frame.event === "assistant.final") {
              const text = frame.data?.text;
              if (typeof text === "string") currentContent[0].text = text;
              resolveAgent({ answer: currentContent, usage: null });
              return;
            }

            if (frame.event === "result") {
              // Tool call completed — do NOT resolve the agent yet; Goose may
              // still write its final text response after this.
              // fall through to add one activity row
            }

            if (frame.event === "error") {
              // Terminal error — resolve now so the UI doesn't spin forever.
              const firstError = !agentResolved;
              resolveAgent({ answer: currentContent, usage: null });
              if (!firstError) return; // duplicate error — skip activity row
              // fall through to add one error activity row
            }

            // Activity rows: only action / result / error (not message)
            setLocalState((prev) => {
              if (prev.id !== conversationId) return prev;
              const messages = [...prev.messages];
              const idx = messages.length - 2;
              const row = messages[idx];
              if (!row || row.role !== "assistant") return prev;
              const prevActs = row.agentActivities || [];
              const activity = normalizeAgentSseActivity(frame);
              messages[idx] = {
                ...row,
                agentActivities: [...prevActs, activity],
                loading: true,
              };
              return { ...prev, messages, ignoreConflict: true };
            });
          },
        });
      }
      let usage = null;
      let process_block = "";
      let inThinking = false;
      let message_text = "";
      for await (const chunk of chatCompletions(conversationForAPI, timeoutAPI, true, agentHooks)) {
        // Async 202: runtime job submitted — SSE drives the bubble, wait for it
        if (chunk?._agentAsync) {
          return async202Promise;
        }
        const delta = chunk?.choices?.[0]?.delta;
        if (chunk?.usage) usage = chunk.usage;
        if (Array.isArray(delta?.tool_calls) && delta.tool_calls.length > 0) {
          try {
            if (delta.tool_calls[0]?.function?.name === "tools.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "error") {
                process_block += "Could not use tools: " + String(arg?.msg) + "\n\n";
              } 
            }
            if (delta.tool_calls[0]?.function?.name === "mcp.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "call") {
                process_block += "Calling MCP server: " + String(arg?.server) 
                + "\n\nfunction: `" 
                + String(arg?.function) 
                + "` with args: `"
                + String(arg?.arguments)
                + "`\n\n";
              } else if (arg.event === "result") {
                process_block += "MCP response received of type `" + String(arg?.type) + "`\n\n";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "rscript.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "preparing_script") {
                process_block += "Running R Script:\n```r\n" + String(arg?.script) + "\n```\n\n";
              } 
              if (arg.event === "error") {
                process_block += "Cannot use Rscript: " + String(arg?.msg) + "\n\n";
              } 
            }
            // Handle web search events
            if (delta.tool_calls[0]?.function?.name === "websearch.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "begin") {
                process_block += "Searching for \"" + arg.query + "\" on ";
              } else if (arg.event === "config") {
                process_block += String(arg?.["search-engine"]) + "\n\n";
              } else if (arg.event === "websearch_done") {
                process_block += "Web search completed. Used " + String(arg.selected) + " relevant sources.\n\n";
              } else if (arg.event === "websearch_page_cache" || arg.event === "fetch") {
                process_block += "Reading source: " + String(arg?.url) + "\n\n";
              } else if (arg.event === "error") {
                process_block += "Websearch Error: " + String(arg?.msg) + "\n\n";
              } else {
                process_block += "";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "arcana.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "accessing") {
                process_block += `Reading arcana "${arg.arcana}" \n\n`;
              } else if (arg.event === "done") {
                process_block += "";// "Arcana retrieval completed.";
              } else {
                process_block += "";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "image.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "image_creation_begin") {
                process_block += `Generating image: "${arg.query}" \n\n`;
              } else if (arg.event === "image_modify_begin") {
                process_block += "Modifying image: " + String(arg?.query) + "\n\n";
              } else if (arg.event === "done") {
                process_block += "";// "Image generation completed.";
              } if (arg.event === "error") {
                process_block += "Image generation failed: " + String(arg?.msg) + "\n\n";
              } else {
                process_block += "";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "video.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "begin") {
                process_block += `Generating video: "${arg.query}" \n\n`;
              } if (arg.event === "error") {
                process_block += "Video generation failed: " + String(arg?.msg) + "\n\n";
              } else {
                process_block += "";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "audio.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "audio_creation_begin") {
                process_block += `Generating audio: "${arg.query}" \n\n`;
              } else if (arg.event === "done") {
                process_block += "";// "Audio generation completed.";
              } if (arg.event === "error") {
                process_block += "Audio generation failed: " + String(arg?.msg) + "\n\n";
              } else {
                process_block += "";
              }
            }
            if (delta.tool_calls[0]?.function?.name === "audio_transcription.event") {
              let arg = delta.tool_calls[0].function.arguments;
              if (typeof arg === "string") arg = JSON.parse(arg);
              if (arg.event === "begin") {
                process_block += `Transcribing audio: `;
              } else if (arg.event === "done") {
                process_block += arg.transcription + "\n\n";// "Audio transcription completed.";
              } if (arg.event === "error") {
                process_block += "Audio transcription failed: " + String(arg?.msg) + "\n\n";
              } else {
                process_block += "";
              }
            }
          } catch (err) {
            console.warn("Didn't understand: ", delta)
          }
        }
        
        // Attempt to receive file
        let fileId = null;
        if (delta?.audio) {
          // Process audio output
          try {
            console.log("Receiving audio...");
            const base64_data = delta.audio?.data;
            const transcript = delta.audio?.transcript;

            const format = delta.audio?.format || "wav";
            const filename = delta.audio?.filename || `output.${format}`;
            const mimeType = format === "mp3" ? "audio/mpeg" : `audio/${format}`;
            fileId = await receiveFile(base64_data, mimeType, filename, conversationId, format);
          } catch (err) {
            console.error("Error receiving audio file:", err);
          }
        } else if (delta?.content && typeof delta.content !== String) {
          // Attempt to save file
            try {
              if (delta.content?.type === "image") {
                // Process image input
                console.log("Receiving image...");
                const base64_dataURL = delta.content?.image_url;

                // Extract base64 and mime type
                const matches = base64_dataURL.match(/^data:(.+);base64,(.*)$/);
                if (!matches) {
                  throw new Error("Invalid base64 image data");
                }

                const mimeType = matches[1];
                const base64Data = matches[2];
                fileId = await receiveFile(base64Data, mimeType, "image_output", conversationId);
              }
            } catch (err) {
              console.error("Error processing image chunk:", err);
              continue;
            }
        }
        if (fileId) {
          // Attach new file to model output
          currentContent.push({"type": "file", "fileId": fileId})
          setLocalState(prev => {
            if (prev.id !== conversationId) {
              return prev;
            }
            const messages = [...prev.messages];
            const idx = messages.length - 2;
            const acts = messages[idx]?.agentActivities;
            messages[idx] = {
              role: "assistant",
              content: currentContent,
              loading: true,
              ...(acts?.length ? { agentActivities: acts } : {}),
            };
            return { ...prev, messages, ignoreConflict: true };
          });
        }
        if (process_block) {
          if (!inThinking) {
            message_text += "<think>";
            inThinking = true;
          }
          message_text += process_block;
          process_block = "";
        }
        if (delta?.content && typeof delta.content === "string") {
          if (inThinking) {
            message_text += "</think>";
            inThinking = false;
          }
          // Process string input
          message_text += delta.content;
        }
        // UI update
        currentContent[0].text = message_text;
        setLocalState(prev => {
          if (prev.id !== conversationId) {
            return prev;
          }
          const messages = [...prev.messages];
          const idx = messages.length - 2;
          const acts = messages[idx]?.agentActivities;
          messages[idx] = {
            role: "assistant",
            content: currentContent,
            loading: true,
            ...(acts?.length ? { agentActivities: acts } : {}),
          };
          return { ...prev, messages, ignoreConflict: true };
        });
      }
      if (inThinking) {
        message_text += "</think>";
        inThinking = false;
        currentContent[0].text = message_text
      }
      return {
        answer: currentContent,
        usage
      }
    }

    // For agent turns: upload any attached files to the session workspace so
    // Goose can read them directly. Inject file paths into the prompt text.
    if (_isAgentTurn) {
      const lastMsg = localState.messages[localState.messages.length - 1];
      const fileItems = (lastMsg?.content || []).filter(
        (item) => item.type === "file" && item.fileId
      );
      if (fileItems.length > 0) {
        const uploaded = [];
        for (const item of fileItems) {
          try {
            const file = await loadFile(item.fileId);
            if (!file) continue;
            const result = await uploadAgentFile(conversationId, file);
            uploaded.push({ name: file.name, path: result.path });
          } catch (err) {
            console.warn("Failed to upload file to agent workspace:", err);
          }
        }
        if (uploaded.length > 0) {
          const note =
            "\n\nFiles uploaded to your workspace:\n" +
            uploaded.map((f) => `- ${f.name} → ${f.path}`).join("\n");
          const msgs = conversationForAPI.messages;
          const lastIdx = msgs.length - 1;
          if (msgs[lastIdx]?.role === "user") {
            const c = msgs[lastIdx].content;
            if (typeof c === "string") {
              msgs[lastIdx] = { ...msgs[lastIdx], content: c + note };
            } else if (Array.isArray(c)) {
              const txt = c.find((x) => x.type === "text");
              if (txt) txt.text += note;
              else c.unshift({ type: "text", text: note });
            }
          }
        }
      }
    }

    let responseContent = "";
    let usage = null;
    let chatChunk = null;
    let meta = undefined;
    let choicesProposed = [];
    let agenticFailure = null;
    try {
      // Get chat completion response
      chatChunk = await getChatChunk(conversationId);
      responseContent = chatChunk?.answer || ""
      usage = chatChunk?.usage;
      meta = {
        model: localState.settings.model?.name || localState.settings.model?.id || "",
        usage
      };
    } catch (error) {
      if (isChatAiAgentModel(localState.settings.model)) {
        const norm = normalizeAgentHttpError(error?.status, error?.message);
        agenticFailure = {
          message: norm.display,
          retryable: norm.retryable,
          status: norm.status,
        };
      } else {
        const errorType = error?.type || "Error";
        const errorMsg = error?.error?.message || error?.error || error?.message || "An unknown error occurred";
        const errorStatus = error?.status ? `(${error.status})` : "";
        notifyError(`${errorType}: ${errorMsg.toString()} ${errorStatus}`);
      }
      console.error(error);
    } finally {
      // Update choices
      if(choicesModule && localState.settings.choiceProposer == 1 && !agenticFailure){
        try {
          const content = localState.messages.map((message) => {
          if (Array.isArray(message.content)){
            return message.role + ": " + message.content[0].text;
          }
          });
          content.push("assistant: " + (responseContent?.[0]?.text ?? ""))
          console.log(content.join("\n\n"))

          const response = await generateChoiceProposal(
            content.join("\n\n")
          );
          choicesProposed = response;
        } catch (error) {
          console.error("Failed to generate choices: ", error.name, error.message);
          notifyError("Failed to generate choices.");
        }
      }

      // Set loading to false
      setLocalState(prev => {
        if (prev.id !== conversationId) {
          // Handle save when conversation is not active, ideally save directly into DB (TODO)
          const inactiveMsgs = [...localState.messages];
          const ia = inactiveMsgs[inactiveMsgs.length - 2]?.agentActivities;
          const im = inactiveMsgs[inactiveMsgs.length - 2]?.agentModels;
          const messages = [...inactiveMsgs,
            {
              role: "assistant",
              content: responseContent?.length
                ? responseContent
                : [{ type: "text", text: "" }],
              loading: false,
              meta,
              ...(ia?.length ? { agentActivities: ia } : {}),
              ...(im?.length ? { agentModels: im } : {}),
              ...(agenticFailure ? { agenticError: agenticFailure } : {}),
            },
            { role: "user", content: [{ type: "text", text: "" }] },
          ];
          updateConversation(
            conversationId,
            { ...localState, messages, hasFirstPrompt: true },
            true
          );
          return prev;
        }
        const choices = choicesProposed;
        const messages = [...prev.messages];
        const idx = messages.length - 2;
        const acts = messages[idx]?.agentActivities;
        const mdls = messages[idx]?.agentModels;
        const baseRow = {
          role: "assistant",
          content: responseContent?.length
            ? responseContent
            : [{ type: "text", text: "" }],
          loading: false,
          ...(mdls?.length ? { agentModels: mdls } : {}),
          meta,
          ...(acts?.length ? { agentActivities: acts } : {}),
        };
        if (agenticFailure) {
          baseRow.agenticError = agenticFailure;
        } else {
          delete baseRow.agenticError;
        }
        messages[idx] = baseRow;
        return { ...prev, messages, choices, flush: true };
      });
    }

    // Handle errors
    // if (response === 401) {
    //   // TODO clean up localState
    //   openModal("errorSessionExpired")
    //   return;
    // } else if (response === 413) {
    //   // TODO clean up localState
    //   openModal("errorBadRequest")
    //   return;
    // }
    
    // If not successful don't continue
    if (!responseContent && !agenticFailure) {
      // TODO clean up localState
      return;
    }

    if (agenticFailure) {
      return;
    }

    delete conversationForAPI.settings?.arcana;

    // Keep last message sent by user for possible memory update
    let newUserMessage = undefined;
    try {
      newUserMessage = conversationForAPI.messages.at(-1).content;
      if (Array.isArray(newUserMessage)) newUserMessage = newUserMessage[0].text;
    } catch (error) {
      console.log("Warning: couldn't find new user message. Memory will not be updated");
    }

    // Generate title if conversation is new
    // Change model if defined in config
    try {
      conversationForAPI.messages = [
        ...conversationForAPI.messages,
        { role: "assistant", content: responseContent },
        { role: "user", content: "" }
      ];
      if (conversationForAPI.messages.length <= 4) {
        const title = await generateTitle(conversationForAPI.messages);
        console.log("Generated title is ", title)
        setLocalState(prev => {
          if (prev.id !== conversationId) {
            updateConversationMeta(conversationId, {title})
            return prev;
          }
          return { ...prev, title, flush: true, };
        });
      }
    } catch (error) {
      console.error("Failed to generate title: ", error);
    }

    // Update memory if enabled
    try {
      if (localState.settings?.memory == 2 && newUserMessage) {
        const memoryResponse = await generateMemory(
          newUserMessage,
          memories
        );
        const cleanedResponse = memoryResponse.replace(/,(\s*[}$])/g, "$1");
        const jsonResponse = JSON.parse(cleanedResponse);
        if (jsonResponse.store) {
          const memoryText = jsonResponse.memory_sentence.trim();
          if (jsonResponse.replace) {
            const line_number = jsonResponse.line_number - 1;
            dispatch(editMemory({ index: line_number, text: memoryText }));
          } else {
            dispatch(addMemory({ text: memoryText }));
          }
          notifySuccess("Memory updated successfully.");
        }
      }
    } catch (error) {
      console.error("Failed to update memory: ", error.name, error.message);
      notifyError("Failed to update memory.");
    }

  } catch (error) {
    // ‌Handle Errors
    if (error.name === "AbortError") {
      notifyError("Request aborted.");
      // For agent models, also cancel the running job on the broker
      if (isChatAiAgentModel(localState.settings.model) && conversationId) {
        try {
          const baseURL = (await import("./agentBrokerSse")).resolveBackendBaseUrl();
          const xUser = (await import("./agentBrokerSse")).resolveAgenticXUser();
          await fetch(
            new URL(`api/agent/sessions/${encodeURIComponent(conversationId)}`, baseURL).toString(),
            { method: "DELETE", headers: { "X-User": xUser } },
          );
        } catch {
          /* best-effort cancel */
        }
      }
    } else if (error.message) {
      console.log(error)
      notifyError(error.message);
    } else {
      notifyError("An unknown error occurred");
    }
  }
};

export default sendMessage;
