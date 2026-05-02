import os

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.admin_routes import router as admin_router
from api.routes import router as api_router
from api.vapi_webhooks import router as vapi_router
from db.database import Base, apply_runtime_migrations, engine
from db.database import SessionLocal
from services.appointment_reminder_job import run_due_reminders
from services.auth_service import ensure_default_admin
from services.notification_service import retry_failed_notifications

scheduler = BackgroundScheduler()

app = FastAPI(
    title="AI Voice Appointment Assistant API",
    version="0.1.0",
)

raw_origins = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _reminder_tick() -> None:
    if os.getenv("REMINDER_JOB_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        return
    db = SessionLocal()
    try:
        run_due_reminders(db)
    finally:
        db.close()


def _notification_retry_tick() -> None:
    if os.getenv("NOTIFICATION_RETRY_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        return
    db = SessionLocal()
    try:
        retry_failed_notifications(db)
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()

    interval = int(os.getenv("REMINDER_JOB_INTERVAL_MINUTES", "5") or "5")
    scheduler.add_job(
        _reminder_tick,
        "interval",
        minutes=max(1, interval),
        id="appointment_reminders",
        replace_existing=True,
    )
    retry_interval = int(os.getenv("NOTIFICATION_RETRY_INTERVAL_MINUTES", "5") or "5")
    scheduler.add_job(
        _notification_retry_tick,
        "interval",
        minutes=max(1, retry_interval),
        id="notification_retry_worker",
        replace_existing=True,
    )
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(api_router)
app.include_router(vapi_router)
app.include_router(admin_router)
