## Table of contents

| | |
|---|---|
| [AI-Powered Hospital Appointment Agent](#ai-powered-hospital-appointment-agent) | Title and tagline |
| [About this project](#about-this-project) | What it is and why it exists |
| [Features](#features) | Main capabilities |
| [Tech stack](#tech-stack) | Technologies used |
| [Architecture](#architecture) | High-level flow |
| [Prerequisites](#prerequisites) | What you need installed |
| [Quick start](#quick-start) | Run backend and frontend locally |
| [Configuration](#configuration) | Local env files (brief) |
| [Database and migrations](#database-and-migrations) | Alembic / PostgreSQL |
| [Vapi (voice AI)](#vapi-voice-ai) | Voice assistant assets |
| [Twilio (SMS and WhatsApp)](#twilio-sms-and-whatsapp) | Reminders |
| [Google Calendar](#google-calendar) | Calendar sync |
| [API reference](#api-reference) | Main HTTP endpoints |
| [Project structure](#project-structure) | Repository layout |
| [Security](#security) | Commits and private data |
| [Contributing & license](#contributing--license) | How to contribute |
| [Author & contact](#author--contact) | Maintainer |

---

# AI-Powered Hospital Appointment Agent

**Voice-first hospital and clinic scheduling** — patients book, reschedule, or cancel through an AI assistant, while staff use a web dashboard for providers, slots, fees, and logs. The backend is **FastAPI** and **PostgreSQL**; voice is **Vapi**; calendar sync is **Google Calendar**; reminders go out over **Twilio** (SMS and optional WhatsApp). The admin UI is **React** and **Vite**.

**Repository:** [github.com/Muqadas1234/Muqadas1234-AI-Powered-hospital-appointment-agent](https://github.com/Muqadas1234/Muqadas1234-AI-Powered-hospital-appointment-agent)

---

## About this project

This project is a **full-stack appointment agent**: the patient talks to an assistant that checks real availability, creates or updates bookings, and keeps the hospital side in sync. Behind the scenes, the same system can **notify** patients before visits and let them **respond** on channels you enable, so the flow feels like a single product rather than a loose demo.

It suits **portfolios**, **final-year or capstone demos**, **health-tech proof-of-concepts**, or as a **starting point** for a real deployment you customize and harden. The focus is on a clear path from **voice intent** to **stored appointment** and **staff visibility**, with room to extend rules, branding, and integrations.

The repo includes the **API**, **migrations**, **background reminder logic**, **Vapi tool + prompt files**, and the **frontend** for both voice and admin. Integrations such as telephony, calendar, and hosting are **your deployment choices** — wire them when you run the app locally or in production.

---

## Features

| Area | Details |
|------|---------|
| Voice booking | Book appointments through conversational AI with confirmation flow |
| Reschedule / cancel | Update or cancel existing appointments; slot release and notifications |
| Provider fees | `fee_pkr` per provider; assistant can state fees naturally to patients |
| Calendar sync | Create/update/delete Google Calendar events when slots change |
| Reminders | SMS and optional WhatsApp reminders (timing is configurable) |
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
git clone https://github.com/Muqadas1234/Muqadas1234-AI-Powered-hospital-appointment-agent.git
cd Muqadas1234-AI-Powered-hospital-appointment-agent
```

### 2. Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows — then edit .env for your setup
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
copy .env.example .env   # Windows — fill in for your Vapi app
npm run dev
```

Open: [http://127.0.0.1:5173](http://127.0.0.1:5173)

---

## Configuration

Copy the example files and adjust them for your machine:

```bash
copy .env.example .env
copy frontend\.env.example frontend\.env
```

Use **`.env.example`** and **`frontend/.env.example`** as the reference while you edit your local files. Do not commit private copies.

---

## Database and migrations

```bash
alembic upgrade head    # apply all migrations
alembic current         # show revision
```

Migrations live in `alembic/versions/` (including provider `fee_pkr` and reminder-related fields).

---

## Vapi (voice AI)

| Asset | Path |
|-------|------|
| Tool definitions | `vapi/tools.json` |
| System / assistant prompt | `vapi/assistant_prompt.txt` |

To push prompt and tools to the Vapi dashboard:

```bash
python -m scripts.sync_vapi
```

For development, expose your API over **HTTPS** (for example a tunnel) so Vapi can reach your tool URLs.

---

## Twilio (SMS and WhatsApp)

Configure your Twilio account and sender numbers for the reminders you want. Point inbound message webhooks at your **public** app URL when you test replies. Keep SMS and WhatsApp setup under **one** Twilio project so credentials stay consistent.

---

## Google Calendar

Create a service account, download its key JSON, share the target calendar with that account, and place the file where your local config expects it. If Calendar is not set up, booking can still run depending on how you deploy; calendar steps are optional for a minimal API-only tryout.

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

## Security

Keep local-only and sensitive material out of git. This repo relies on **`.gitignore`** for common cases; review before every push.

---

## Contributing & license

Pull requests and issues are welcome. Add a **LICENSE** file when you decide how others may use this project.

---

## Author & contact

| | |
|---|---|
| **Maintainer** | Muqadas |
| **Email** | [muqadasakram.13@gmail.com](mailto:muqadasakram.13@gmail.com) |

For collaboration, deployment questions, or licensing, use the email above.

---

**Built with:** FastAPI · PostgreSQL · React · Vapi · Google Calendar · Twilio
