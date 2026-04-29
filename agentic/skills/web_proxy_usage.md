---
skill_name: "web_proxy_usage"
description: "How HTTP(S) traffic uses the campus proxy inside the sandbox"
framework: "*"
---

# Web egress & proxy

- Outbound **`web_search`** / **`web_browse`** honour **`HTTPS_PROXY` / `HTTP_PROXY`** injected by the broker (often `http://www-cache.gwdg.de:3128` on GWDG systems).
- **`NO_PROXY`** may include the cluster LLM hostname so prompts stay on-net without traversing the web proxy.
- Hosts matching `MCP_SERVER_WEB_BLOCKED_HOST_SUFFIXES` (`.internal`, `.corp`, …) are refused before DNS — do not rely on “just try it” probes.
- Responses are capped (~5 MB for browse); prefer concise URLs.

Use **`web_search`** for discovery and **`web_browse`** only when an HTTP GET of a specific document is necessary.
