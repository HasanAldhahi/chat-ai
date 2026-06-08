/**
 * Live indicator of which LLM model(s) are handling an agent turn.
 *
 * Driven by `model.active` SSE events: the orchestrator appears first, then a
 * chip is added for every delegated specialist. A pulsing dot marks the model
 * that is currently running; a check marks ones that have finished.
 */

const CAPABILITY_ICON = {
  orchestrator: "🧠",
  coding: "💻",
  summarization: "📝",
  vision: "👁️",
  heavy_logic: "⚙️",
};

const CAPABILITY_LABEL = {
  orchestrator: "orchestrator",
  coding: "coding",
  summarization: "summarizing",
  vision: "vision",
  heavy_logic: "reasoning",
};

function RunningDot() {
  return (
    <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
    </span>
  );
}

export default function AgentModelBar({ models }) {
  if (!models?.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-0.5 -mb-1" aria-live="polite">
      {models.map((m) => {
        const running = m.status === "running";
        const errored = !!m.error;
        const icon = CAPABILITY_ICON[m.capability] ?? "🤖";
        const label = CAPABILITY_LABEL[m.capability] ?? m.capability;
        return (
          <span
            key={m.key}
            title={m.task || m.error || m.model}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] leading-none transition-colors ${
              errored
                ? "border-red-300 bg-red-50 dark:border-red-800/60 dark:bg-red-950/30"
                : running
                  ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800/60 dark:bg-emerald-950/30"
                  : "border-slate-200 bg-slate-50 dark:border-slate-700/60 dark:bg-slate-800/40"
            }`}
          >
            <span aria-hidden="true">{icon}</span>
            <span className="font-mono text-slate-600 dark:text-slate-300">
              {m.model}
            </span>
            <span className="text-slate-400 dark:text-slate-500">· {label}</span>
            {errored ? (
              <span aria-label="failed">⚠️</span>
            ) : running ? (
              <RunningDot />
            ) : (
              <span className="text-emerald-500" aria-label="done">
                ✓
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}
