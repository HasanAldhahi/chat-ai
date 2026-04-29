"""Newline-delimited JSON-RPC stdin → synchronous HTTP POST to chat-ai MCP /rpc."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8080/rpc"


def main() -> None:
    url = os.environ.get("CHAT_AI_MCP_HTTP_URL", DEFAULT_URL).strip()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = urllib.request.Request(
            url,
            data=line.encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                out = resp.read().decode()
        except urllib.error.HTTPError as e:
            out = e.read().decode()
        except OSError as e:
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e)},
                        "id": None,
                    }
                )
            )
            sys.stdout.write("\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
