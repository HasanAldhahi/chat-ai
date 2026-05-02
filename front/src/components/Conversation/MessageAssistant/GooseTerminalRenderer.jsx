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

    // Separator line ────────────
    if (/^[─\-]{10,}$/.test(s)) {
      if (tool) { segments.push(tool); tool = null; }
      continue;
    }

    // Tool start: ▸ name  or  ▶ name
    const toolM = s.match(/^[▸▶]\s+(.+?)\s*$/);
    if (toolM) {
      flushText();
      if (tool) segments.push(tool);
      tool = { type: "tool", name: toolM[1].trim(), args: [], outputLines: [] };
      continue;
    }

    if (tool) {
      // Indented key: value lines before first output → args
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
  shell:   { label: "shell",   accent: "text-green-400" },
  bash:    { label: "bash",    accent: "text-green-400" },
  python:  { label: "python",  accent: "text-yellow-300" },
  analyze: { label: "analyze", accent: "text-blue-400" },
  tree:    { label: "tree",    accent: "text-yellow-400" },
  read:    { label: "read",    accent: "text-sky-400" },
  write:   { label: "write",   accent: "text-orange-400" },
  search:  { label: "search",  accent: "text-purple-400" },
  web:     { label: "web",     accent: "text-cyan-400" },
};

function toolMeta(name) {
  const k = name.toLowerCase().split(/\s+/)[0];
  return TOOL_META[k] ?? { label: name, accent: "text-purple-400" };
}

// ── ToolBlock ─────────────────────────────────────────────────
const PREVIEW = 10;

function ToolBlock({ seg }) {
  const [open, setOpen] = useState(false);
  const meta = toolMeta(seg.name);
  const outLines = seg.outputLines.filter((l) => l.trim());
  const hasOut = outLines.length > 0;
  const bigOut = outLines.length > PREVIEW;

  const primary = seg.args[0];
  const extra = seg.args.slice(1);

  return (
    <div className="rounded-md border border-gray-700/50 overflow-hidden font-mono text-xs bg-gray-950 dark:bg-gray-950/80 my-1">
      {/* header row */}
      <button
        type="button"
        onClick={() => hasOut && setOpen((o) => !o)}
        className={`w-full flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 py-1.5
          bg-gray-800/70 dark:bg-gray-900/60 text-left
          ${hasOut ? "cursor-pointer hover:bg-gray-800" : "cursor-default"}`}
      >
        {/* tool name */}
        <span className={`font-semibold ${meta.accent}`}>▶ {meta.label}</span>

        {/* primary arg (most important, e.g. command / path) */}
        {primary && (
          <span className="text-gray-300 truncate max-w-[40ch] sm:max-w-[60ch]">
            <span className="text-gray-500 mr-0.5">{primary.key}:</span>
            {primary.val}
          </span>
        )}

        {/* extra args hidden on narrow screens */}
        {extra.map((a, i) => (
          <span key={i} className="hidden sm:inline text-gray-500">
            {a.key}: <span className="text-gray-400">{a.val}</span>
          </span>
        ))}

        {/* line count + toggle */}
        {hasOut && (
          <span className="ml-auto shrink-0 text-[10px] text-gray-500 select-none">
            {open ? "▲ collapse" : `▼ ${outLines.length} line${outLines.length !== 1 ? "s" : ""}`}
          </span>
        )}
      </button>

      {/* output area */}
      {hasOut && open && (
        <div className="px-3 py-2 border-t border-gray-700/30 text-gray-300 overflow-x-auto">
          <pre className="whitespace-pre-wrap break-words leading-relaxed text-[11px]">
            {(bigOut ? outLines.slice(0, PREVIEW) : outLines).join("\n")}
          </pre>
          {bigOut && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setOpen(true); }}
              className="mt-1 text-[10px] text-blue-400 hover:text-blue-300 cursor-pointer"
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
    <div className="space-y-1">
      {segments.map((seg, i) => {
        if (seg.type === "tool") return <ToolBlock key={i} seg={seg} />;
        return (
          <MarkdownRenderer
            key={i}
            isLoading={isLoading && i === segments.length - 1}
            renderMode={renderMode}
          >
            {seg.content}
          </MarkdownRenderer>
        );
      })}
    </div>
  );
}
