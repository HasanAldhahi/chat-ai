import React, { useState } from "react";
import MarkdownRenderer from "./MarkdownRenderer";

// ── banner filter ─────────────────────────────────────────────
function isBannerLine(line) {
  const s = line.trim();
  if (!s) return false;
  return (
    /^[_\\/<>()\|L*●·\s\-─]+$/.test(s) ||
    s.includes("goose is ready") ||
    s.includes("new session") ||
    /^\w*[_)]\s+\d{8}_\d+\s*·/.test(s)
  );
}

// ── parser ────────────────────────────────────────────────────
function parseGooseOutput(text) {
  if (!text?.trim()) return [];
  const lines = text.split("\n");
  const segments = [];
  let tool = null;
  let textLines = [];

  function flushText() {
    const t = textLines.join("\n").trim();
    textLines = [];
    if (t) segments.push({ type: "text", content: t });
  }

  for (const line of lines) {
    if (isBannerLine(line)) continue;
    const s = line.trim();

    if (/^[─\-]{10,}$/.test(s)) {
      if (tool) { segments.push(tool); tool = null; }
      continue;
    }

    const toolM = s.match(/^[▸▶]\s+(.+?)\s*$/);
    if (toolM) {
      flushText();
      if (tool) segments.push(tool);
      tool = { type: "tool", name: toolM[1].trim(), args: [], outputLines: [] };
      continue;
    }

    if (tool) {
      const isArg =
        /^ {2,}[\w][\w .-]*: .+/.test(line) && tool.outputLines.length === 0;
      if (isArg) {
        const ci = s.indexOf(":");
        tool.args.push({ key: s.slice(0, ci).trim(), val: s.slice(ci + 1).trim() });
      } else {
        tool.outputLines.push(line);
      }
      continue;
    }

    textLines.push(line);
  }

  if (tool) segments.push(tool);
  flushText();
  return segments;
}

// ── tool metadata ─────────────────────────────────────────────
const TOOL_META = {
  shell:   { icon: "⚡", label: "Shell",   color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/25", border: "border-emerald-200 dark:border-emerald-800/50" },
  bash:    { icon: "⚡", label: "Bash",    color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/25", border: "border-emerald-200 dark:border-emerald-800/50" },
  python:  { icon: "🐍", label: "Python",  color: "text-amber-600 dark:text-amber-400",    bg: "bg-amber-50 dark:bg-amber-950/25",    border: "border-amber-200 dark:border-amber-800/50" },
  analyze: { icon: "🔍", label: "Analyze", color: "text-blue-600 dark:text-blue-400",      bg: "bg-blue-50 dark:bg-blue-950/25",      border: "border-blue-200 dark:border-blue-800/50" },
  tree:    { icon: "🌲", label: "Tree",    color: "text-green-600 dark:text-green-400",    bg: "bg-green-50 dark:bg-green-950/25",    border: "border-green-200 dark:border-green-800/50" },
  read:    { icon: "📄", label: "Read",    color: "text-sky-600 dark:text-sky-400",        bg: "bg-sky-50 dark:bg-sky-950/25",        border: "border-sky-200 dark:border-sky-800/50" },
  write:   { icon: "✏️", label: "Write",   color: "text-orange-600 dark:text-orange-400",  bg: "bg-orange-50 dark:bg-orange-950/25",  border: "border-orange-200 dark:border-orange-800/50" },
  search:  { icon: "🔎", label: "Search",  color: "text-violet-600 dark:text-violet-400",  bg: "bg-violet-50 dark:bg-violet-950/25",  border: "border-violet-200 dark:border-violet-800/50" },
  web:     { icon: "🌐", label: "Web",     color: "text-cyan-600 dark:text-cyan-400",      bg: "bg-cyan-50 dark:bg-cyan-950/25",      border: "border-cyan-200 dark:border-cyan-800/50" },
};

const DEFAULT_META = {
  icon: "🔧",
  color: "text-slate-600 dark:text-slate-400",
  bg: "bg-slate-50 dark:bg-slate-800/40",
  border: "border-slate-200 dark:border-slate-700/60",
};

function toolMeta(name) {
  const k = name.toLowerCase().split(/\s+/)[0];
  const base = TOOL_META[k] ?? DEFAULT_META;
  return { ...base, label: base.label ?? name };
}

// ── pulsing execution dot ─────────────────────────────────────
function PulsingDot() {
  return (
    <span className="relative flex h-2 w-2 shrink-0" aria-hidden="true">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
    </span>
  );
}

// ── ToolBlock ─────────────────────────────────────────────────
const PREVIEW = 10;

function ToolBlock({ seg, isExecuting }) {
  const [argsOpen, setArgsOpen] = useState(false);
  const [outOpen, setOutOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const meta = toolMeta(seg.name);
  const outLines = seg.outputLines.filter((l) => l.trim());
  const hasOut = outLines.length > 0;
  const hasArgs = seg.args.length > 0;
  const bigOut = outLines.length > PREVIEW;

  return (
    <div className={`rounded-xl border my-1.5 overflow-hidden ${meta.bg} ${meta.border}`}>
      {/* Header row */}
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <span className="text-base leading-none shrink-0" aria-hidden="true">
          {meta.icon}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] font-bold uppercase tracking-wider ${meta.color}`}>
              {meta.label}
            </span>
            {isExecuting && !hasOut && (
              <span className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                <PulsingDot />
                Executing…
              </span>
            )}
            {hasOut && (
              <span className="text-[10px] text-slate-400 dark:text-slate-500">
                {outLines.length} line{outLines.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          {/* Primary arg shown inline as a subtitle */}
          {seg.args[0] && (
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400 truncate font-mono">
              <span className="opacity-60">{seg.args[0].key}: </span>
              <span className="text-slate-700 dark:text-slate-300">{seg.args[0].val}</span>
            </p>
          )}
        </div>

        {/* Accordion pill buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {hasArgs && (
            <button
              type="button"
              onClick={() => setArgsOpen((o) => !o)}
              className="text-[10px] px-2 py-0.5 rounded-full bg-white/60 dark:bg-white/10 border border-transparent hover:border-current text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-all"
            >
              {argsOpen ? "hide args" : "args"}
            </button>
          )}
          {hasOut && (
            <button
              type="button"
              onClick={() => setOutOpen((o) => !o)}
              className="text-[10px] px-2 py-0.5 rounded-full bg-white/60 dark:bg-white/10 border border-transparent hover:border-current text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-all"
            >
              {outOpen ? "▲ hide" : "▼ output"}
            </button>
          )}
        </div>
      </div>

      {/* Args accordion */}
      {argsOpen && hasArgs && (
        <div className="border-t border-white/50 dark:border-white/10 px-3 py-2 bg-white/30 dark:bg-black/10">
          <dl className="space-y-1">
            {seg.args.map((a, i) => (
              <div key={i} className="flex gap-2 text-[11px] font-mono">
                <dt className="text-slate-400 dark:text-slate-500 shrink-0">{a.key}:</dt>
                <dd className="text-slate-700 dark:text-slate-300 break-all">{a.val}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Output accordion */}
      {outOpen && hasOut && (
        <div className="border-t border-white/50 dark:border-white/10">
          <pre className="px-3 py-2.5 text-[11px] leading-relaxed font-mono text-slate-700 dark:text-slate-300 bg-white/40 dark:bg-black/20 whitespace-pre-wrap break-words overflow-x-auto max-h-64">
            {(bigOut && !showAll ? outLines.slice(0, PREVIEW) : outLines).join("\n")}
          </pre>
          {bigOut && !showAll && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="w-full text-[11px] py-1.5 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 bg-white/20 dark:bg-black/10 transition-colors border-t border-white/30 dark:border-white/10"
            >
              +{outLines.length - PREVIEW} more lines
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── main component ────────────────────────────────────────────
export default function GooseTerminalRenderer({ text, isLoading, renderMode }) {
  const segments = parseGooseOutput(text);
  if (!segments.length) return null;

  return (
    <div className="space-y-0.5">
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1;
        if (seg.type === "tool") {
          return (
            <ToolBlock key={i} seg={seg} isExecuting={isLoading && isLast} />
          );
        }
        return (
          <MarkdownRenderer
            key={i}
            isLoading={isLoading && isLast}
            renderMode={renderMode}
          >
            {seg.content}
          </MarkdownRenderer>
        );
      })}
    </div>
  );
}
