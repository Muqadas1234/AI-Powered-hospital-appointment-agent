import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/vapi", tags=["vapi"])

LOG_FILE = Path("vapi_webhook_events.jsonl")


@router.post("/webhook")
def vapi_webhook(payload: dict[str, Any]):
    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")

    event_type = payload.get("type", "unknown")
    return {"status": "received", "event_type": event_type}
