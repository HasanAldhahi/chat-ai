import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import fs from "fs";

const CONFIG_LOCATION = process.env.CONFIG_LOCATION || "../secrets/front.json";

function loadFrontConfig() {
  const raw = fs.readFileSync(CONFIG_LOCATION, "utf8");
  return JSON.parse(raw);
}

/**
 * Backend origin from front.json backendPath — used only for the dev-server proxy target.
 */
function backendOriginFromSecrets(config) {
  const fallback = "http://127.0.0.1:8081";
  const p = typeof config.backendPath === "string" ? config.backendPath.trim() : "";
  if (!p) return fallback;
  try {
    return new URL(p).origin;
  } catch {
    return fallback;
  }
}

function devProxyForBackend(targetOrigin) {
  const cfg = {
    changeOrigin: true,
    target: targetOrigin,
    secure: false,
  };
  return {
    "/models": { ...cfg },
    "/user": { ...cfg },
    "/documents": { ...cfg },
    "/chat/completions": { ...cfg },
    "/api": { ...cfg },
  };
}

/** True when npm run dev (or bare `vite`); false for preview / build / tests. */
function useSameOriginApiInDev(command) {
  if (process.env.CHAT_AI_DEV_PROXY === "false") return false;
  if (command !== "serve") return false;
  if (process.argv.includes("preview")) return false;
  const le = process.env.npm_lifecycle_event;
  if (le === "test") return false;
  return le === "dev" || le === undefined;
}

export default defineConfig(({ command }) => {
  let port = 8080;
  try {
    const config = loadFrontConfig();
    console.log(`Config loaded from ${CONFIG_LOCATION}:`, config);

    if (typeof config.port === "number" && config.port > 0) {
      port = config.port;
      console.log("Port:", port);
    } else {
      console.warn(
        "Invalid port in config.json. Falling back to default port 8080.",
      );
    }

    const sameOriginApi = useSameOriginApiInDev(command);
    const backendProxyOrigin = backendOriginFromSecrets(config);

    for (const [key, value] of Object.entries(config)) {
      if (key === "modelsPath") {
        process.env["VITE_MODELS_ENDPOINT"] = sameOriginApi
          ? "/models"
          : value;
        console.log("Models path:", process.env["VITE_MODELS_ENDPOINT"]);
      } else if (key === "backendPath") {
        process.env["VITE_BACKEND_ENDPOINT"] = sameOriginApi ? "" : value;
        console.log("Backend path:", process.env["VITE_BACKEND_ENDPOINT"] || "(same origin)");
      } else if (key === "userDataPath") {
        process.env["VITE_USERDATA_ENDPOINT"] = sameOriginApi ? "/user" : value;
        console.log("User data path:", process.env["VITE_USERDATA_ENDPOINT"]);
      } else if (key === "default") {
        process.env["VITE_DEFAULT_SETTINGS"] = JSON.stringify(value);
        console.log("Default settings:", JSON.stringify(value));
      } else if (key === "titleGenerationModel") {
        process.env["VITE_TITLE_GENERATION_MODEL"] = value;
        console.log("Title generation model:", value);
      } else if (key === "memoryGenerationModel") {
        process.env["VITE_MEMORY_GENERATION_MODEL"] = value;
        console.log("Memory generation model:", value);
      } else if (key === "proposalGenerationModel") {
        process.env["VITE_PROPOSAL_GENERATION_MODEL"] = value;
        console.log("Proposal generation model:", value);
      } else if (key === "announcement") {
        process.env["VITE_ANNOUNCEMENT"] = value;
        console.log("Announcement:", value);
      } else if (key === "modules") {
        console.log("Modules:", JSON.stringify(value));
        try {
          process.env["VITE_MODULE_TOOLS"] = value?.tools || false;
          process.env["VITE_MODULE_FEEDBACK"] = value?.feedback || false;
          process.env["VITE_MODULE_CHOICES"] = value?.choices || false;
        } catch (e) {
          console.log("Error while parsing modules: ", e);
        }
      }
    }

    if (sameOriginApi) {
      console.log(
        `Dev API proxy enabled → ${backendProxyOrigin} (set CHAT_AI_DEV_PROXY=false to disable)`,
      );
    }

    const serverCfg = {
      port,
      open: false,
      ...(sameOriginApi ? { proxy: devProxyForBackend(backendProxyOrigin) } : {}),
    };

    return {
      plugins: [react(), tailwindcss()],
      base: "/",
      server: serverCfg,
      preview: {
        port,
        open: false,
      },
    };
  } catch (error) {
    console.error("Failed to load config.json:", error);
    process.exit(1);
  }
});
