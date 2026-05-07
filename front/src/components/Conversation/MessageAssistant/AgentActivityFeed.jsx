import { toolIconForType } from "../../../utils/agentBrokerSse";

const SNIPPET = 400;

function SystemSpinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"
      aria-hidden="true"
    />
  );
}

function formatTimestamp(ts) {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleString(undefined, {
      dateStyle: "short",
      timeStyle: "medium",
    });
  } catch {
    return String(ts);
  }
}

export default function AgentActivityFeed({ activities, onToggleExpand }) {
  if (!activities?.length) return null;

  // For agent runs, filter to only show error events (result is shown by the terminal renderer)
  const all = activities.filter((a) => a.sseEvent === "error" || a.sseEvent === "action");
  if (!all.length) return null;

  // Check the full activities array — Goose real output arrives as "message"
  // or "result" events that never enter `all`, so checking only `all` keeps
  // hasRealActivity false forever.
  const hasRealActivity = activities.some((a) => a.type !== "system");
  // Hide system boot events once real activity has arrived — they only belong
  // at the start of the first session; subsequent messages never emit them.
  const visible = hasRealActivity
    ? all.filter((a) => a.type !== "system")
    : all;
  if (!visible.length) return null;

  return (
    <div
      className="flex flex-col gap-2 mb-2 w-full max-w-full text-left"
      aria-live="polite"
    >
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
            className={`rounded-lg border text-sm px-2.5 py-2 sm:px-3 max-w-full break-words ${
              isErr
                ? "bg-red-50 border-red-200 text-red-900 dark:bg-red-950/50 dark:border-red-800 dark:text-red-100"
                : isSystem
                  ? "bg-blue-50 border-blue-200 text-blue-900 dark:bg-blue-950/50 dark:border-blue-800 dark:text-blue-100"
                  : "bg-gray-100 border-gray-200 text-gray-800 dark:bg-gray-800/80 dark:border-gray-600 dark:text-gray-100"
            }`}
          >
            <div className="flex items-start gap-2 min-w-0">
              <span className="text-base shrink-0 mt-0.5" aria-hidden="true">
                {isErr ? "⚠️" : isActiveSystem ? <SystemSpinner /> : toolIconForType(a.type)}
              </span>
              <div className="flex-1 min-w-0 space-y-1">
                <div className="text-[11px] sm:text-xs opacity-75 tabular-nums">
                  {formatTimestamp(a.timestamp)}
                  {a.type ? ` · ${a.type}` : ""}
                  {isErr && a.code ? ` · ${a.code}` : ""}
                </div>
                {shown ? (
                  <pre className="whitespace-pre-wrap font-sans text-xs sm:text-sm leading-snug">
                    {shown}
                  </pre>
                ) : null}
                {truncated ? (
                  <button
                    type="button"
                    className="text-xs text-primary dark:text-tertiary underline cursor-pointer"
                    onClick={() => onToggleExpand(a.id)}
                  >
                    Show more
                  </button>
                ) : null}
                {a.expanded && body.length > SNIPPET ? (
                  <button
                    type="button"
                    className="text-xs text-primary dark:text-tertiary underline cursor-pointer"
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
