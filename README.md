# AI-Powered Hospital Appointment Agent

Voice-first appointment system for hospitals and clinics: patients book, reschedule, or cancel by talking to an AI assistant. The backend syncs with **Google Calendar**, sends **SMS** and **WhatsApp** reminders via **Twilio**, and exposes an **admin dashboard** (React) for providers, slots, appointments, fees, and notification logs.

**Repository:** [github.com/Muqadas1234/AI-Powered-hospital-appointment-agent](https://github.com/Muqadas1234/AI-Powered-hospital-appointment-agent)

---

## Table of contents

| Section | Description |
|--------|-------------|
| [Overview](#overview) | What this project does |
| [Features](#features) | Capabilities at a glance |
| [Tech stack](#tech-stack) | Languages, frameworks, and services |
| [Architecture](#architecture) | High-level flow |
| [Prerequisites](#prerequisites) | What you need installed |
| [Quick start](#quick-start) | Run backend and frontend locally |
| [Configuration](#configuration) | Environment variables and secrets |
| [Database and migrations](#database-and-migrations) | PostgreSQL / Alembic |
| [Vapi (voice AI)](#vapi-voice-ai) | Assistant, tools, sync script |
| [Twilio (SMS and WhatsApp)](#twilio-sms-and-whatsapp) | Reminders and inbound replies |
| [Google Calendar](#google-calendar) | Service account setup |
| [API reference](#api-reference) | Main HTTP endpoints |
| [Project structure](#project-structure) | Repository layout |
| [Security notes](#security-notes) | What never to commit |

---

## Overview

The **AI Hospital Appointment Agent** connects three layers:

1. **Voice (Vapi)** — The patient speaks; the assistant uses tool calls to read availability and complete bookings.
2. **API (FastAPI)** — Validates requests, persists data, drives notifications, and integrates with Google Calendar.
3. **Admin UI (React + Vite)** — Staff manage providers (including **consultation fee in PKR**), time slots, FAQs, appointments, and notification history.

Scheduled jobs (**APScheduler**) send reminders before appointments; patients can confirm or cancel via **SMS/WhatsApp** replies where configured.

---

## Features

| Area | Details |
|------|---------|
| Voice booking | Book appointments through conversational AI with confirmation flow |
| Reschedule / cancel | Update or cancel existing appointments; slot release and notifications |
| Provider fees | `fee_pkr` per provider; assistant can state fees naturally to patients |
| Calendar sync | Create/update/delete Google Calendar events when slots change |
| Reminders | SMS and optional WhatsApp reminders (lead time configurable in minutes) |
| Admin auth | JWT login for protected admin routes |
| Idempotency | Optional `idempotency_key` on booking to avoid duplicate appointments |
| Tool security | Optional `TOOL_API_KEY` for agent-facing tool endpoints |

---

## Tech stack

| Layer | Technology |
|-------|------------|
| API | Python 3, **FastAPI**, Pydantic |
| Database | **PostgreSQL** (recommended), SQLAlchemy, **Alembic** |
| Voice | **Vapi** (`@vapi-ai/web` in frontend; tools + prompt in `vapi/`) |
| Calendar | **Google Calendar API** (service account JSON) |
| Messaging | **Twilio** (REST via `requests` — SMS + WhatsApp) |
| Scheduling | **APScheduler** |
| Admin UI | **React 18**, **Vite 5** |
| Auth | JWT (python-jose), passlib/bcrypt |

---

## Architecture

```text
Patient (voice) ──► Vapi ──► Tool HTTPS ──► FastAPI ──► PostgreSQL
                              │                │
                              │                ├──► Google Calendar
                              │                └──► Twilio (SMS / WhatsApp)
Staff (browser) ──► React admin ──► FastAPI (JWT)
```

---

## Prerequisites

- **Python** 3.10+ (recommended)
- **Node.js** 18+ (for the frontend)
- **PostgreSQL** (or adapt `DATABASE_URL` if you use another supported backend)
- **Google Cloud** project with Calendar API enabled (optional but recommended for live calendar)
- **Vapi** account for voice (optional for API-only testing)
- **Twilio** account for SMS/WhatsApp (optional)

---

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/Muqadas1234/AI-Powered-hospital-appointment-agent.git
cd AI-Powered-hospital-appointment-agent
```

### 2. Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows — edit .env with your values
# cp .env.example .env   # macOS/Linux
alembic upgrade head
python -m scripts.seed    # optional sample data
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3. Frontend (admin + voice UI)

```bash
cd frontend
npm install
copy .env.example .env   # set VITE_VAPI_PUBLIC_KEY and VITE_VAPI_ASSISTANT_ID
npm run dev
```

Open: [http://127.0.0.1:5173](http://127.0.0.1:5173)

---

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Backend secrets and URLs — **create from `.env.example`**, never commit |
| `frontend/.env` | Vapi public key and assistant ID for the browser |
| `google-service-account.json` | Google service account key — **never commit** (path set in `.env`) |

Copy examples:

```bash
copy .env.example .env
copy frontend\.env.example frontend\.env
```

Important variables (see `.env.example` for the full list):

| Variable | Role |
|----------|------|
| `DATABASE_URL` | SQLAlchemy URL (PostgreSQL) |
| `JWT_SECRET_KEY` / `ADMIN_*` | Admin login |
| `TOOL_API_KEY` | Optional header for tool routes |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Calendar JSON key path |
| `TWILIO_*` / `TWILIO_WHATSAPP_FROM` | SMS and WhatsApp |
| `REMINDER_SMS_LEAD_MINUTES` / `REMINDER_WHATSAPP_LEAD_MINUTES` | Minutes before appointment to send |
| `PUBLIC_BASE_URL` | Public HTTPS base (e.g. ngrok) for webhooks |
| `VAPI_*` | Private key, assistant ID, ngrok URL for `sync_vapi` |

---

## Database and migrations

```bash
alembic upgrade head    # apply all migrations
alembic current         # show revision
```

Migrations live in `alembic/versions/` (including provider `fee_pkr` and reminder fields).

---

## Vapi (voice AI)

| Asset | Path |
|-------|------|
| Tool definitions | `vapi/tools.json` |
| System / assistant prompt | `vapi/assistant_prompt.txt` |

Sync prompt and tools to the Vapi dashboard (requires `VAPI_PRIVATE_API_KEY`, `VAPI_ASSISTANT_ID`, and a reachable `VAPI_NGROK_URL`):

```bash
python -m scripts.sync_vapi
```

Expose your FastAPI base URL over **HTTPS** (for example **ngrok**) so Vapi can call tool endpoints in development.

---

## Twilio (SMS and WhatsApp)

1. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_PHONE` for SMS.
2. For WhatsApp sandbox or approved sender, set `TWILIO_WHATSAPP_FROM` and `WHATSAPP_REMINDER_ENABLED=true`.
3. Point Twilio inbound webhooks to your deployed **`PUBLIC_BASE_URL`** routes for reminder replies (as configured in your app — see `PUBLIC_BASE_URL` in `.env`).

Use one Twilio project for all numbers and sandbox access to avoid mismatched credentials.

---

## Google Calendar

1. Create a **service account** in Google Cloud and download the JSON key.
2. Share the target calendar with the service account email.
3. Set `GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_CALENDAR_ID` in `.env`.

If Calendar is not configured, booking can still proceed with a safe sync-skipped path depending on your deployment.

---

## API reference

### Agent / tool routes (examples)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tools/get_faq_answer` | FAQ lookup |
| GET | `/api/v1/tools/get_providers` | List providers (includes `fee_pkr` when set) |
| GET | `/api/v1/tools/get_available_slots` | Free slots for a provider |
| POST | `/api/v1/tools/check_calendar` | Conflict check |
| POST | `/api/v1/tools/book_appointment` | Create booking |
| POST | `/api/v1/tools/cancel_appointment` | Cancel |
| POST | `/api/v1/tools/reschedule_appointment` | Reschedule |

### Example: `book_appointment`

`POST /api/v1/tools/book_appointment`

```json
{
  "user_name": "Ali Khan",
  "user_phone": "+923001234567",
  "provider_id": 1,
  "slot_id": 2,
  "confirmed_by_user": true,
  "confirmation_text": "yes please book it",
  "idempotency_key": "optional-unique-key-12345678"
}
```

### Admin and auth (examples)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Admin JWT |
| GET | `/api/v1/admin/appointments` | List appointments |
| GET/POST | `/api/v1/admin/providers` | Providers CRUD |
| GET/POST | `/api/v1/admin/slots` | Slots |
| GET/POST | `/api/v1/admin/faqs` | FAQs |
| GET | `/api/v1/admin/notifications` | Notification log |

Full detail: **Swagger UI** at `/docs` when the server is running.

---

## Project structure

| Path | Contents |
|------|----------|
| `app/` | FastAPI application entry |
| `api/` | Routes: public tools, admin, Vapi webhooks |
| `db/` | SQLAlchemy models and database session |
| `schemas/` | Pydantic DTOs |
| `services/` | Booking, calendar, notifications, reminders, auth |
| `alembic/` | Migrations |
| `scripts/` | Seed, Vapi sync, utilities |
| `vapi/` | `tools.json`, `assistant_prompt.txt` |
| `frontend/` | React + Vite admin and voice client |
| `tests/` | Automated tests |

---

## Security notes

| Never commit | Reason |
|--------------|--------|
| `.env` | Live secrets and API keys |
| `frontend/.env` | Vapi browser credentials |
| `google-service-account.json` | Full access to Calendar as service account |
| Local `*.db` | May contain PII from development |

This repository uses `.gitignore` to exclude those files. Rotate any key that was ever pushed to a remote by mistake.

---

## Contributing and license

Issues and pull requests are welcome. Add a **LICENSE** file if you plan to open-source under a specific terms.

---

**Built with:** FastAPI · PostgreSQL · React · Vapi · Google Calendar · Twilio
