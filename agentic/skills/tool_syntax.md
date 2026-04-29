---
skill_name: "tool_syntax"
description: "JSON-RPC envelope for MCP tools exposed at POST /rpc"
frameworks:
  - openhands
  - goose
  - opencode
---

# MCP tool calls (chat-ai HTTP JSON-RPC)

Single endpoint: **`POST ${MCP_SERVER_URL}/rpc`** with `Content-Type: application/json`.

## `list_tools`

```json
{"jsonrpc":"2.0","id":1,"method":"list_tools","params":{}}
```

Response: `result.tools[]` entries with `name`, `description`, `input_schema`.

## `call_tool`

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "call_tool",
  "params": {
    "name": "fs_read",
    "arguments": { "path": "/workspace/README.md" }
  }
}
```

Errors return JSON-RPC `error` with `data.tool_error` for policy violations (read the string and adjust the plan).

## `get_skills`

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "call_tool",
  "params": {
    "name": "get_skills",
    "arguments": { "framework": "openhands" }
  }
}
```

Omit `framework` to use `MCP_SERVER_AGENT_FRAMEWORK` (set by the agent launcher). The result lists Markdown bodies you can paste into planning before coding.
