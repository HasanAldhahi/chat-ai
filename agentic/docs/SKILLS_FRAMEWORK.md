# Agent skills framework (Task 4.4)

Operational snippets ship from **`agentic/skills/`**: flat **`*.md`** files with a **`---`** fenced YAML header (`skill_name`, `description`, `framework`, …).

Images bake **`agentic/skills/` → `/skills`** via **`containers/mcp/Apptainer.def`** (`MCP_SERVER_SKILLS_DIR`, default `/skills`).

## MCP surface

- **`call_tool` → `get_skills`** accepts optional `arguments.framework`; otherwise the server uses **`MCP_SERVER_AGENT_FRAMEWORK`** (explicit defaults from each launcher: `openhands`, `goose`, `opencode`).
- Responses list `{ skill_name, description, markdown }`; agents should consult them when planning Slurm, proxy, or MCP-syntax work.

## Matching rules

- **`framework: "*"`** attaches to every framework ID.
- **`frameworks: [openhands, goose, opencode]`** restricts to that union.
- **`framework: openhands`** matches only that single ID (case-insensitive).
- **Empty** `framework` argument plus empty env selects **wildcard (`*`)** skills **only** — framework-specific notes require an explicit ID or launcher default.

## Cache

Skills are read once per process and directory key (`mcp_server/skills/loader.py`). Rebuild the MCP process after changing files on disk.

## Editing

Add or remove Markdown under **`agentic/skills/`** and rebuild **`mcp.sif`**. Invalid files log a warning at load time and are skipped.
