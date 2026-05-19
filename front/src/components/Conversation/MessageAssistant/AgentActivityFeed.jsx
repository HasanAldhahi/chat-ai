import { toolIconForType } from "../../../utils/agentBrokerSse";

const SNIPPET = 400;

function SystemSpinner() {
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0 mt-0.5" aria-hidden="true">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
    </span>
  );
}

function formatTimestamp(ts) {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleTimeString(undefined, { timeStyle: "short" });
  } catch {
    return String(ts);
  }
}

export default function AgentActivityFeed({ activities, onToggleExpand }) {
  if (!activities?.length) return null;

  const all = activities.filter((a) => a.sseEvent === "error" || a.sseEvent === "action");
  if (!all.length) return null;

  const hasRealActivity = activities.some((a) => a.type !== "system");
  const visible = hasRealActivity
    ? all.filter((a) => a.type !== "system")
    : all;
  if (!visible.length) return null;

  return (
    <div className="flex flex-col gap-1.5 mb-2 w-full" aria-live="polite">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5 px-0.5">
        Thoughts &amp; Actions
      </p>

      {visible.map((a) => {
        const isErr = a.sseEvent === "error";
        const isSystem = !isErr && a.type === "system";
        const isActiveSystem = isSystem && !hasRealActivity;
        const primary = a.message || "";
        const secondary = a.output || "";
        const body = [primary, secondary].filter(Boolean).join("\n\n");
        const truncated = !a.expanded && body.length > SNIPPET;
        const shown = truncated ? `${body.slice(0, SNIPPET)}…` : body;

        return (
          <div
            key={a.id}
            className={`rounded-xl border text-sm px-3 py-2.5 max-w-full break-words ${
              isErr
                ? "bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-800/60"
                : isSystem
                  ? "bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800/60"
                  : "bg-slate-50 border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/60"
            }`}
          >
            <div className="flex items-start gap-2.5 min-w-0">
              {/* Icon */}
              <span className="shrink-0 text-base leading-none mt-0.5" aria-hidden="true">
                {isErr ? "⚠️" : isActiveSystem ? <SystemSpinner /> : toolIconForType(a.type)}
              </span>

              <div className="flex-1 min-w-0 space-y-1">
                {/* Meta row: type label + timestamp */}
                <div className="flex items-center gap-2 flex-wrap">
                  {a.type && (
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wide ${
                        isErr
                          ? "text-red-600 dark:text-red-400"
                          : isSystem
                            ? "text-blue-600 dark:text-blue-400"
                            : "text-slate-500 dark:text-slate-400"
                      }`}
                    >
                      {isActiveSystem ? "Starting up…" : a.type}
                    </span>
                  )}
                  <span className="text-[10px] text-slate-400 dark:text-slate-500 tabular-nums ml-auto">
                    {formatTimestamp(a.timestamp)}
                    {isErr && a.code ? ` · ${a.code}` : ""}
                  </span>
                </div>

                {/* Body */}
                {shown ? (
                  <p className="text-xs leading-relaxed text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {shown}
                  </p>
                ) : null}

                {truncated ? (
                  <button
                    type="button"
                    className="text-xs text-blue-500 dark:text-blue-400 hover:underline cursor-pointer"
                    onClick={() => onToggleExpand(a.id)}
                  >
                    Show more
                  </button>
                ) : null}

                {a.expanded && body.length > SNIPPET ? (
                  <button
                    type="button"
                    className="text-xs text-blue-500 dark:text-blue-400 hover:underline cursor-pointer"
                    onClick={() => onToggleExpand(a.id)}
                  >
                    Show less
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
