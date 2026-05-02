import { useState, useEffect } from "react";

const COMMANDS = [
  { name: "model",  description: "Switch the active model" },
  { name: "tokens", description: "Show token usage for this conversation" },
];

function estimateTokens(messages) {
  let chars = 0;
  for (const msg of messages ?? []) {
    const c = msg.content;
    if (typeof c === "string") chars += c.length;
    else if (Array.isArray(c)) {
      for (const part of c) if (part?.text) chars += part.text.length;
    }
  }
  return Math.round(chars / 4);
}

export default function SlashCommandPalette({
  prompt,
  onDone,        // onDone(newPromptValue) — caller sets prompt + closes
  localState,
  setLocalState,
  modelsData,
}) {
  const [mode, setMode] = useState("commands"); // "commands" | "models" | "tokens"
  const [activeIdx, setActiveIdx] = useState(0);

  const query   = prompt.startsWith("/") ? prompt.slice(1).toLowerCase() : "";
  const filtered = COMMANDS.filter((c) => c.name.startsWith(query));

  const currentModel  = localState?.settings?.model;
  const tokenEstimate = estimateTokens(localState?.messages);
  const msgCount      = (localState?.messages ?? []).filter((m) => m.role !== "system").length;

  // Stay visible while in a sub-mode even if prompt no longer starts with "/"
  const isVisible = prompt.startsWith("/") || mode !== "commands";

  // Reset back to command list when user edits the "/" query
  useEffect(() => {
    if (mode === "commands") setActiveIdx(0);
  }, [query, mode]);

  // Close completely when prompt is fully cleared
  useEffect(() => {
    if (prompt === "") { setMode("commands"); setActiveIdx(0); }
  }, [prompt]);

  const selectCommand = (cmd) => {
    if (cmd.name === "model")  { setMode("models");  setActiveIdx(0); }
    if (cmd.name === "tokens") { setMode("tokens"); }
  };

  const selectModel = (model) => {
    setLocalState((prev) => ({
      ...prev,
      settings: { ...prev.settings, model },
    }));
    onDone("");
  };

  // Keyboard navigation — capture phase so we intercept before textarea's Enter
  useEffect(() => {
    if (!isVisible) return;

    const items = mode === "models" ? (modelsData ?? []) : filtered;

    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onDone("");
        setMode("commands");
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, items.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        if (mode === "commands" && filtered[activeIdx]) {
          selectCommand(filtered[activeIdx]);
        } else if (mode === "models" && modelsData?.[activeIdx]) {
          selectModel(modelsData[activeIdx]);
        } else if (mode === "tokens") {
          onDone("");
          setMode("commands");
        }
      }
    };

    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [isVisible, mode, activeIdx, filtered, modelsData]);

  if (!isVisible) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 z-50 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-bg_secondary_dark shadow-xl overflow-hidden">
      {mode === "tokens" && (
        <div className="p-4 text-sm">
          <div className="flex items-center gap-2 mb-3">
            <span className="font-medium text-gray-900 dark:text-white">Token Usage</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">(estimate)</span>
          </div>
          <div className="space-y-2 text-gray-600 dark:text-gray-300">
            <div className="flex justify-between">
              <span>Estimated tokens</span>
              <span className="font-mono font-semibold text-gray-900 dark:text-white">
                {tokenEstimate.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Messages</span>
              <span className="font-mono font-semibold text-gray-900 dark:text-white">{msgCount}</span>
            </div>
            <div className="flex justify-between">
              <span>Active model</span>
              <span className="font-mono font-semibold text-gray-900 dark:text-white truncate ml-4 max-w-[60%] text-right">
                {currentModel?.name ?? currentModel?.id ?? "—"}
              </span>
            </div>
          </div>
          <button
            onClick={() => { onDone(""); setMode("commands"); }}
            className="mt-3 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            Press Esc to close
          </button>
        </div>
      )}

      {mode === "models" && (
        <div className="max-h-64 overflow-y-auto">
          <div className="px-3 py-2 text-xs font-medium text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800 sticky top-0 bg-white dark:bg-bg_secondary_dark">
            Select model  <span className="font-normal opacity-60">↑↓ navigate · Enter select · Esc cancel</span>
          </div>
          {(modelsData ?? []).length === 0 && (
            <div className="px-4 py-3 text-sm text-gray-400">No models available</div>
          )}
          {(modelsData ?? []).map((model, i) => (
            <button
              key={model.id}
              onClick={() => selectModel(model)}
              className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between gap-2 transition-colors ${
                i === activeIdx
                  ? "bg-purple-50 dark:bg-purple-900/20"
                  : "hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
            >
              <span className={`truncate ${
                i === activeIdx
                  ? "text-purple-700 dark:text-purple-300"
                  : "text-gray-700 dark:text-gray-200"
              } ${model.id === currentModel?.id ? "font-semibold" : ""}`}>
                {model.name ?? model.id}
              </span>
              {model.id === currentModel?.id && (
                <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-300">
                  active
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {mode === "commands" && (
        <>
          {filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-400 dark:text-gray-500">
              No command matches <span className="font-mono">{prompt}</span>
            </div>
          ) : (
            filtered.map((cmd, i) => (
              <button
                key={cmd.name}
                onClick={() => selectCommand(cmd)}
                className={`w-full text-left px-4 py-2.5 flex items-center gap-3 text-sm transition-colors ${
                  i === activeIdx
                    ? "bg-purple-50 dark:bg-purple-900/20"
                    : "hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
              >
                <span className={`font-mono font-semibold ${
                  i === activeIdx
                    ? "text-purple-600 dark:text-purple-300"
                    : "text-gray-900 dark:text-white"
                }`}>
                  /{cmd.name}
                </span>
                <span className="text-gray-400 dark:text-gray-500 text-xs">
                  {cmd.description}
                </span>
                <span className="ml-auto text-xs text-gray-300 dark:text-gray-600">Enter ↵</span>
              </button>
            ))
          )}
        </>
      )}
    </div>
  );
}
