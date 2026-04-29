---
skill_name: "file_permissions"
description: "Allowed roots, symlink rules, and size caps for fs_* tools"
framework: "*"
---

# File tools policy (chat-ai MCP)

- Reads may target **`/workspace`** and **`/home/user`** (read-only home). Writes are limited to **`/workspace`** unless the broker changes `MCP_SERVER_FS_*` roots.
- Paths are normalised and must not escape the allowed root via `..`, absolute symlinks, or tricky Unicode. Symlink hops that exit the sandbox are rejected.
- **`fs_read`** caps file size (**10 MB default**); **`fs_write`** caps payload (**1 MB**). Larger artefacts should be chunked or streamed by the agent differently.
- Listing (`fs_list`) is non-recursive and capped (**2 000** entries).

If `fs_read` fails with `path_not_allowed`, re-check the literal path spelling and workspace bind mount.
