import os

from fastapi import Header, HTTPException


def verify_tool_api_key(x_tool_api_key: str | None = Header(default=None)) -> None:
    """
    Optional tool authentication:
    - If TOOL_API_KEY is not set, requests are allowed (local/dev mode).
    - If TOOL_API_KEY is set, matching X-Tool-Api-Key header is required.
    """
    expected = os.getenv("TOOL_API_KEY", "").strip()
    if not expected:
        return
    if not x_tool_api_key or x_tool_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing tool API key.")
