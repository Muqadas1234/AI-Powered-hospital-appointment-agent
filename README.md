# AI-Powered Hospital Appointment Agent

Voice-driven booking for clinics and hospitals: patients talk to an assistant to book, reschedule, or cancel; staff manage everything in a web dashboard. Built with **FastAPI**, **PostgreSQL**, **React**, **Vapi**, **Google Calendar**, and **Twilio** (SMS / WhatsApp reminders).

---

## Contents

- [About](#about)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Integrations](#integrations)
- [API](#api)
- [Repository layout](#repository-layout)
- [Security](#security)
- [Author](#author)

---

## About

This project is a **full-stack demo** you can extend into a real product: conversational scheduling, optional calendar sync, automated reminders, and an admin UI for providers, slots, consultation fees, and logs. It fits **portfolios**, **course projects**, and **health-tech prototypes**.

---

## Features

| Area | What it does |
|------|----------------|
| Voice | Natural-language booking with confirmation |
| Admin | Providers, slots, fees (PKR), FAQs, appointments, notification history |
| Calendar | Google Calendar sync for booked slots |
| Reminders | SMS and optional WhatsApp before appointments |
| API | Tool endpoints for the voice stack; JWT-protected admin routes |

---

## Tech stack

| Layer | Stack |
|--------|--------|
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Frontend | React, Vite |
| Voice | Vapi |
| Calendar | Google Calendar API |
| Messaging | Twilio |

---

## Architecture

```text
Patient (voice) → Vapi → HTTPS tools → FastAPI → PostgreSQL
                                      ↓
                              Calendar / messaging
Staff (browser) → React → FastAPI (JWT)
```

---

## Getting started

**Requirements:** Python 3.10+, Node.js 18+, PostgreSQL.

```bash
git clone https://github.com/Muqadas1234/Muqadas1234-AI-Powered-hospital-appointment-agent.git
cd Muqadas1234-AI-Powered-hospital-appointment-agent
```

**Backend**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Before first run, add the **local** config files your machine needs (see the included `*.example` files in the project root and `frontend/`). Interactive API docs: `http://127.0.0.1:8000/docs`.

---

## Integrations

- **Vapi** — Assistant behaviour and tools live under `vapi/`; use the project’s sync script if you update prompt or tools.
- **Google Calendar** — Optional; service account key stays on the server only.
- **Twilio** — Optional; used for transactional SMS / WhatsApp where you enable it.

---

## API

Main tool routes live under `/api/v1/tools/` (booking, slots, providers, FAQ, etc.). Admin routes under `/api/v1/admin/`. Full list and request shapes: **Swagger** at `/docs` while the server runs.

---

## Repository layout

| Path | Role |
|------|------|
| `app/` | Application entry |
| `api/` | HTTP routes (tools, admin, webhooks) |
| `services/` | Booking, notifications, calendar, auth |
| `db/`, `schemas/` | Models and DTOs |
| `alembic/` | Migrations |
| `vapi/` | Voice assistant prompt and tool definitions |
| `frontend/` | Admin + voice UI |
| `scripts/` | Seeds and helpers |

---

## Security

Do not commit private credentials, keys, or personal database passwords. The project is set up to ignore common local secret files; keep real values only on your machine or secure deployment.

---

## Author

**Muqadas** — [muqadasakram.13@gmail.com](mailto:muqadasakram.13@gmail.com)

---

*FastAPI · PostgreSQL · React · Vapi · Google Calendar · Twilio*
