import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "vapi" / "assistant_prompt.txt"
TOOLS_PATH = ROOT / "vapi" / "tools.json"
VAPI_API_BASE = "https://api.vapi.ai"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def is_backend_reachable(base_url: str) -> bool:
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/openapi.json",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=10,
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        return "/api/v1/tools/get_providers" in (payload.get("paths") or {})
    except Exception:
        return False


def detect_ngrok_url() -> str:
    configured = os.getenv("VAPI_NGROK_URL", "").strip().rstrip("/")
    if configured and configured.lower() != "auto" and is_backend_reachable(configured):
        return configured

    try:
        tunnels = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=5).json().get("tunnels", [])
    except Exception as exc:
        raise SystemExit(
            "Could not detect ngrok URL. Start ngrok first with: "
            "C:\\tools\\ngrok\\ngrok.exe http 8000"
        ) from exc

    https_urls = [t.get("public_url", "").rstrip("/") for t in tunnels if t.get("public_url", "").startswith("https://")]
    for url in https_urls:
        if is_backend_reachable(url):
            return url

    raise SystemExit(
        "No active ngrok HTTPS tunnel is routing to this backend. "
        "Run backend + ngrok, then retry."
    )


def load_tools(ngrok_url: str) -> list[dict]:
    tool_api_key = os.getenv("TOOL_API_KEY", "").strip()

    tools = json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
    synced_tools: list[dict] = []

    for tool in tools:
        current = dict(tool)
        url = current["url"]
        if "/api/v1/" in url:
            suffix = url.split("/api/v1/", 1)[1]
            current["url"] = f"{ngrok_url}/api/v1/{suffix}"
        else:
            current["url"] = ngrok_url

        raw_headers = dict(current.get("headers", {}))
        raw_headers["ngrok-skip-browser-warning"] = "true"
        if tool_api_key:
            raw_headers["x-tool-api-key"] = tool_api_key
        else:
            raw_headers.pop("x-tool-api-key", None)

        headers_schema = {
            "type": "object",
            "properties": {
                key: {"type": "string", "default": str(value)}
                for key, value in raw_headers.items()
            },
        }

        tool_body_schema = None
        if current.get("method", "").upper() != "GET":
            # Use the JSON schema parameters as the request body schema so Vapi
            # sends the tool-call arguments as the HTTP JSON body.
            tool_body_schema = current.get("parameters") or {"type": "object"}

        api_request_tool: dict = {
            "type": "apiRequest",
            "name": current["name"],
            "description": current.get("description", ""),
            "method": current.get("method", "GET").upper(),
            "url": current["url"],
            "headers": headers_schema,
        }
        if tool_body_schema is not None:
            api_request_tool["body"] = tool_body_schema

        synced_tools.append(api_request_tool)

    return synced_tools


def build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_assistant(api_key: str, assistant_id: str) -> dict:
    response = requests.get(
        f"{VAPI_API_BASE}/assistant/{assistant_id}",
        headers=build_headers(api_key),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def update_assistant(api_key: str, assistant_id: str, payload: dict) -> dict:
    response = requests.patch(
        f"{VAPI_API_BASE}/assistant/{assistant_id}",
        headers=build_headers(api_key),
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise SystemExit(f"Vapi update failed: {response.status_code} {response.text[:1000]}")
    response.raise_for_status()
    return response.json()


def main() -> None:
    load_dotenv()

    api_key = require_env("VAPI_PRIVATE_API_KEY")
    assistant_id = require_env("VAPI_ASSISTANT_ID")
    ngrok_url = detect_ngrok_url()
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    tools = load_tools(ngrok_url)

    assistant = get_assistant(api_key, assistant_id)
    model = dict(assistant.get("model") or {})
    model["messages"] = [{"role": "system", "content": prompt}]
    model["tools"] = tools
    model.pop("toolIds", None)

    # Opening line when the call connects (Vapi plays this before the user speaks).
    first_message = os.getenv("VAPI_FIRST_MESSAGE", "").strip()
    if not first_message:
        first_message = (
            "Assalamualaikum, welcome to our hospital helpline. "
            "I'm here to help you book or manage appointments. How may I assist you today?"
        )

    payload: dict = {
        "model": model,
        "firstMessage": first_message,
    }

    # Optional: set in .env to switch to a more natural voice, then run this script again.
    # Example: VAPI_VOICE_PROVIDER=11labs  VAPI_VOICE_ID=Rachel
    voice_provider = os.getenv("VAPI_VOICE_PROVIDER", "").strip()
    voice_id = os.getenv("VAPI_VOICE_ID", "").strip()
    if voice_provider and voice_id:
        payload["voice"] = {"provider": voice_provider, "voiceId": voice_id}

    updated = update_assistant(api_key, assistant_id, payload)

    print("Vapi assistant updated successfully.")
    print("Assistant ID:", updated.get("id", assistant_id))
    print("Synced tools:", ", ".join(tool["name"] for tool in tools))
    print("Ngrok URL:", ngrok_url)


if __name__ == "__main__":
    main()
