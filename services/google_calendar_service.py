import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Pakistan is UTC+5. Used when ZoneInfo fails (e.g. Windows without tzdata).
PKT_OFFSET = timezone(timedelta(hours=5))


def _resolve_tz(timezone_name: str):
    """Return (IANA name for API, tzinfo for datetimes). Never treat clinic wall-clock as UTC."""
    name = (timezone_name or "Asia/Karachi").strip() or "Asia/Karachi"
    try:
        return name, ZoneInfo(name)
    except Exception:
        # Fallback: fixed offset so 10:00 AM stays 10:00 AM local, not 10:00 UTC (which shows as 3 PM PKT).
        if name in ("Asia/Karachi", "Pakistan", "PKT"):
            return "Asia/Karachi", PKT_OFFSET
        return "UTC", timezone.utc


def create_google_calendar_event(
    *,
    summary: str,
    description: str,
    start_datetime: datetime,
    duration_minutes: int = 30,
    end_datetime: datetime | None = None,
) -> tuple[str, str | None]:
    service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()
    timezone_name = os.getenv("APP_TIMEZONE", "Asia/Karachi").strip() or "Asia/Karachi"

    if not service_account_path or not os.path.exists(service_account_path):
        return "Calendar sync skipped: service account file not configured.", None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return "Calendar sync skipped: Google Calendar dependencies not installed.", None

    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=SCOPES,
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    timezone_name, tzinfo = _resolve_tz(timezone_name)

    # Keep event time aligned with local clinic timezone.
    if start_datetime.tzinfo is None:
        start_local = start_datetime.replace(tzinfo=tzinfo)
    else:
        start_local = start_datetime.astimezone(tzinfo)
    if end_datetime is None:
        end_local = start_local + timedelta(minutes=duration_minutes)
    else:
        if end_datetime.tzinfo is None:
            end_local = end_datetime.replace(tzinfo=tzinfo)
        else:
            end_local = end_datetime.astimezone(tzinfo)

    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_local.isoformat(),
            "timeZone": timezone_name,
        },
        "end": {
            "dateTime": end_local.isoformat(),
            "timeZone": timezone_name,
        },
    }

    created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
    event_id = created_event.get("id", "unknown")
    return f"Calendar event created successfully (event_id={event_id}).", event_id


def delete_google_calendar_event(event_id: str) -> tuple[str, bool]:
    """Remove an event from the configured clinic calendar. Second value True if event is gone (deleted or 404)."""
    service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()

    if not event_id or not event_id.strip():
        return "Calendar delete skipped: no event id.", True

    if not service_account_path or not os.path.exists(service_account_path):
        return "Calendar delete skipped: service account file not configured.", False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        return "Calendar delete skipped: Google Calendar dependencies not installed.", False

    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=SCOPES,
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id.strip()).execute()
        return f"Calendar event removed (event_id={event_id}).", True
    except HttpError as exc:
        if getattr(exc, "resp", None) is not None and exc.resp.status == 404:
            return "Calendar event already removed or not found.", True
        return f"Calendar delete failed: {exc}", False
