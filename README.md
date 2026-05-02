# AI Voice Appointment Assistant - MVP + Phase 2

This is the first MVP implementation for your appointment assistant.
It exposes agent-friendly APIs that Vapi/OpenAI can call as tools.

## Implemented Features

- FAQ tool (`get_faq_answer`)
- Provider lookup (`get_providers`)
- Slot lookup (`get_available_slots`)
- Appointment conflict check (`check_calendar`)
- Appointment booking (`book_appointment`)
- Appointment cancellation (`cancel_appointment`)
- Appointment rescheduling (`reschedule_appointment`)
- Google Calendar sync service with safe fallback
- JWT-based admin auth (`/api/v1/auth/login`)
- Admin appointment APIs (`/api/v1/admin/appointments`)
- Notification pipeline (email + SMS with delivery logs)
- Vapi webhook receiver (`/api/v1/vapi/webhook`)
- React voice caller client scaffold (`frontend`)
- Idempotent booking/rescheduling support with `idempotency_key`
- Optional tool API key validation (`TOOL_API_KEY`)

## Tech

- FastAPI
- SQLAlchemy
- PostgreSQL (default via `.env`) or SQLite fallback
- Google Calendar API
- React + Vite

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy env file:
   - `copy .env.example .env` (Windows)
4. Seed sample data:
   - `python -m scripts.seed`
5. Run server:
   - `uvicorn app.main:app --reload`
6. Open docs:
   - `http://127.0.0.1:8000/docs`

## Alembic Migrations

Use Alembic for schema migration management:

1. Run migrations:
   - `alembic upgrade head`
2. Check current revision:
   - `alembic current`
3. Create new migration:
   - `alembic revision -m "your_change_name"`

## Google Calendar Setup

1. Create a Google Cloud project and enable Calendar API.
2. Create a service account and download JSON key file.
3. Place the key file in project root (example: `google-service-account.json`).
4. Update `.env`:
   - `GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json`
   - `GOOGLE_CALENDAR_ID=primary` (or specific calendar id)

If this is not configured, booking still works and returns a safe "sync skipped" message.

## Tool Endpoints for Vapi

- `POST /api/v1/tools/get_faq_answer`
- `GET /api/v1/tools/get_providers?service=dentist`
- `GET /api/v1/tools/get_available_slots?provider_id=1`
- `POST /api/v1/tools/check_calendar`
- `POST /api/v1/tools/book_appointment`
- `POST /api/v1/tools/cancel_appointment`
- `POST /api/v1/tools/reschedule_appointment`
- `POST /api/v1/vapi/webhook`
- `POST /api/v1/auth/login`
- `GET /api/v1/admin/appointments`
- `GET /api/v1/admin/appointments/{appointment_id}`
- `GET /api/v1/admin/notifications`
- `GET /api/v1/admin/providers`
- `POST /api/v1/admin/providers`
- `GET /api/v1/admin/slots`
- `POST /api/v1/admin/slots`
- `GET /api/v1/admin/faqs`
- `POST /api/v1/admin/faqs`

Vapi configs are included in:

- `vapi/tools.json`
- `vapi/assistant_prompt.txt`

## Sync Vapi via API

If you do not want to manually update the Vapi dashboard, you can sync the
assistant prompt and tools using the script below.

1. Add these values to `.env`:
   - `VAPI_PRIVATE_API_KEY`
   - `VAPI_ASSISTANT_ID`
   - `VAPI_NGROK_URL`
2. Run:
   - `python -m scripts.sync_vapi`

What it does:

- loads `vapi/assistant_prompt.txt`
- loads `vapi/tools.json`
- rewrites tool URLs to your current `VAPI_NGROK_URL`
- injects `TOOL_API_KEY` into tool headers if present
- updates the assistant through the Vapi REST API

## Frontend Voice Caller (Phase 2)

1. Go to `frontend` folder.
2. Install packages:
   - `npm install`
3. Configure env:
   - copy `frontend/.env.example` to `frontend/.env`
   - set `VITE_VAPI_PUBLIC_KEY`
   - set `VITE_VAPI_ASSISTANT_ID`
   - set `VITE_BACKEND_URL` (default `http://127.0.0.1:8000`)
4. Start UI:
   - `npm run dev`
5. Open:
   - `http://127.0.0.1:5173`

## Example Booking Request

`POST /api/v1/tools/book_appointment`

```json
{
  "user_name": "Ali Khan",
  "user_email": "ali@example.com",
  "provider_id": 1,
  "slot_id": 2
}
```

## Remaining for Full Production

1. Expose backend publicly with HTTPS for Vapi tools (ngrok or deployment).
2. Enable `TOOL_API_KEY` and add `X-Tool-Api-Key` header in Vapi tools.
3. Configure SMTP/Twilio for real notification delivery.
4. Add retries/alerting around external failures (calendar provider outages, etc.).
5. Add organization-level multi-tenant support.
