"""Session file upload — lets the browser push files into a session workspace.

POST /api/sessions/{session_id}/files
  Multipart: field name "file"
  Returns: { "path": "/workspace/<filename>", "name": "<filename>", "size": <bytes> }

The workspace directory is the same one the local executor binds into the
Goose container at /workspace, so Goose can read any uploaded file immediately.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Header
from fastapi.responses import JSONResponse

log = logging.getLogger("agentic.files")
router = APIRouter()

# Mirror the path used by LocalExecutor: <repo>/agentic/var/jobs/sessions/<session_id>
_WORKSPACE_ROOT = Path(
    os.path.dirname(__file__), "..", "..", "var", "jobs", "sessions"
).resolve()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/api/sessions/{session_id}/files")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    x_user: str = Header(default=""),
):
    workspace = _WORKSPACE_ROOT / session_id
    workspace.mkdir(parents=True, exist_ok=True)

    # Sanitise filename — strip path separators
    filename = Path(file.filename or "upload").name
    dest = workspace / filename

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    dest.write_bytes(data)

    log.info(
        "file_uploaded",
        extra={
            "session_id": session_id,
            "user_id": x_user,
            "upload_filename": filename,
            "bytes": len(data),
        },
    )

    return JSONResponse({
        "path": f"/workspace/{filename}",
        "name": filename,
        "size": len(data),
    })
