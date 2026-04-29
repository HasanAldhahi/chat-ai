# Goose agent image (Task 4.1) — scaffold

Full packaging mirrors `containers/openhands/`: derive from `../mcp/mcp.sif`, add
Goose runtime MCP client + launcher, broker-injected `LLM_*` and proxy env.

**Status:** scaffold only — operator completes recipe + `build_image.sh` using
OpenHands layout as template. Cluster integration test: TBD.
