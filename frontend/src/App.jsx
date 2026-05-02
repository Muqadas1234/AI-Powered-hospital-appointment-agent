import { useEffect, useMemo, useRef, useState } from "react";
import Vapi from "@vapi-ai/web";
import { startConnectingRing } from "./callRingtone.js";

const tabs = ["providers", "slots", "appointments", "faqs", "notifications"];
const tabLabels = {
  providers: "Providers",
  slots: "Slots",
  appointments: "Appointments",
  faqs: "FAQs",
  notifications: "Notifications",
};
const moduleDescriptions = {
  providers: "Manage doctors, services, and consultation fees.",
  slots: "Create and manage appointment slot availability.",
  appointments: "Track booking status, reminders, and patient responses.",
  faqs: "Maintain FAQ answers used by the assistant.",
  notifications: "Review delivery logs across SMS and WhatsApp.",
};

function parseAdminPageFromHash() {
  const hash = window.location.hash || "";
  const match = hash.match(/^#\/admin\/([a-z_]+)$/i);
  if (!match) return "home";
  const page = String(match[1] || "").toLowerCase();
  return tabs.includes(page) ? page : "home";
}

const APP_NAME = "CareVoice";
const APP_TAGLINE = "Hospital appointment helpline";

function formatDisplayTime(value) {
  if (value == null || value === "") return "—";
  const raw = String(value).trim();
  const match = raw.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (!match) return raw;
  let hour = Number(match[1]);
  const minute = match[2];
  const suffix = hour >= 12 ? "PM" : "AM";
  hour = hour % 12;
  if (hour === 0) hour = 12;
  return `${hour}:${minute} ${suffix}`;
}

export default function App() {
  const publicKey = import.meta.env.VITE_VAPI_PUBLIC_KEY;
  const assistantId = import.meta.env.VITE_VAPI_ASSISTANT_ID;
  // Empty = relative URLs → Vite dev proxy forwards /api to FastAPI (see vite.config.js).
  // Set VITE_BACKEND_URL only when the UI and API are on different hosts (e.g. production).
  const rawBackend = import.meta.env.VITE_BACKEND_URL;
  const apiBase =
    rawBackend != null && String(rawBackend).trim() !== ""
      ? String(rawBackend).replace(/\/$/, "")
      : "";
  const vapiRef = useRef(null);
  const listenersAttachedRef = useRef(false);
  const ringtoneStopRef = useRef(null);

  const [panel, setPanel] = useState("user");
  const [adminPage, setAdminPage] = useState(() => parseAdminPageFromHash());
  const [adminUnlocked, setAdminUnlocked] = useState(false);
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem("admin_token") || "");
  const [adminLogin, setAdminLogin] = useState({ username: "", password: "" });

  const [status, setStatus] = useState("Idle");
  const [isCalling, setIsCalling] = useState(false);
  const [callStartedAtMs, setCallStartedAtMs] = useState(null);
  const [callElapsedSec, setCallElapsedSec] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [providers, setProviders] = useState([]);
  const [slots, setSlots] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [faqs, setFaqs] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [providerForm, setProviderForm] = useState({ name: "", service: "", fee_pkr: "" });
  const [slotForm, setSlotForm] = useState({ provider_id: "", date: "", time: "10:00:00", end_time: "10:30:00" });
  const [faqForm, setFaqForm] = useState({ question: "", answer: "" });
  const [bulkSlotForm, setBulkSlotForm] = useState({ provider_id: "", start_date: "", days: "7", times: "10:00,12:00,15:00", duration_minutes: "30" });

  const [providerEditId, setProviderEditId] = useState(null);
  const [providerEdit, setProviderEdit] = useState({ name: "", service: "", fee_pkr: "", is_active: true });
  const [slotEditId, setSlotEditId] = useState(null);
  const [slotEdit, setSlotEdit] = useState({ date: "", time: "10:00:00", end_time: "10:30:00" });
  const [faqEditId, setFaqEditId] = useState(null);
  const [faqEdit, setFaqEdit] = useState({ question: "", answer: "", is_active: true });
  const [cancelModalId, setCancelModalId] = useState(null);
  const [cancelReason, setCancelReason] = useState(
    "Emergency — doctor unavailable. You may book another time through our assistant helpline.",
  );

  const endpoint = useMemo(() => `${apiBase}/api/v1/admin`, [apiBase]);

  const formatVapiError = (event) => {
    if (!event) return "Unknown error.";
    if (typeof event === "string") return event;
    if (event instanceof Error) return event.message || String(event);
    return JSON.stringify(event);
  };


  const callTimerLabel = useMemo(() => {
    const mm = String(Math.floor(callElapsedSec / 60)).padStart(2, "0");
    const ss = String(callElapsedSec % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }, [callElapsedSec]);

  const apiRequest = async (path, options = {}, useAdminAuth = true) => {
    const response = await fetch(`${endpoint}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(useAdminAuth && adminToken ? { Authorization: `Bearer ${adminToken}` } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });
    if (!response.ok) {
      const body = await response.text();
      if (response.status === 401) {
        localStorage.removeItem("admin_token");
        setAdminToken("");
        setAdminUnlocked(false);
        throw new Error("Session expired. Please login again.");
      }
      throw new Error(body || `HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
  };

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const [providerRows, slotRows, appointmentRows, faqRows, notificationRows] = await Promise.all([
        apiRequest("/providers?include_inactive=true"),
        apiRequest("/slots"),
        apiRequest("/appointments?limit=200&offset=0"),
        apiRequest("/faqs?include_inactive=true"),
        apiRequest("/notifications?limit=100&offset=0"),
      ]);
      setProviders(providerRows || []);
      setSlots(slotRows || []);
      setAppointments((appointmentRows && appointmentRows.items) || []);
      setFaqs(faqRows || []);
      setNotifications((notificationRows && notificationRows.items) || []);
    } catch (err) {
      setError(`Admin load failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!publicKey) {
      vapiRef.current = null;
      listenersAttachedRef.current = false;
      return;
    }
    if (!vapiRef.current) vapiRef.current = new Vapi(publicKey);
    if (!listenersAttachedRef.current) {
      vapiRef.current.on("call-start", () => {
        setStatus("Connected — speak naturally");
      });
      vapiRef.current.on("speech-start", () => {
        const stop = ringtoneStopRef.current;
        if (stop) {
          stop();
          ringtoneStopRef.current = null;
        }
      });
      vapiRef.current.on("call-end", () => {
        const stop = ringtoneStopRef.current;
        if (stop) {
          stop();
          ringtoneStopRef.current = null;
        }
        setStatus("Call ended");
        setIsCalling(false);
        setCallStartedAtMs(null);
        setCallElapsedSec(0);
      });
      vapiRef.current.on("error", (event) => {
        const stop = ringtoneStopRef.current;
        if (stop) {
          stop();
          ringtoneStopRef.current = null;
        }
        setError(`Vapi error: ${formatVapiError(event)}`);
        setStatus("Idle");
        setIsCalling(false);
        setCallStartedAtMs(null);
        setCallElapsedSec(0);
      });
      listenersAttachedRef.current = true;
    }
  }, [publicKey]);

  useEffect(() => {
    if (adminToken) {
      setAdminUnlocked(true);
      loadDashboard();
    }
  }, [adminToken]);

  useEffect(() => {
    if (!adminUnlocked || !adminToken) return;
    const timer = setInterval(() => {
      loadDashboard();
    }, 15000);
    return () => clearInterval(timer);
  }, [adminUnlocked, adminToken]);

  useEffect(() => {
    document.body.classList.toggle("call-overlay-open", isCalling);
    return () => document.body.classList.remove("call-overlay-open");
  }, [isCalling]);

  useEffect(() => {
    if (!isCalling || !callStartedAtMs) return;
    const timer = window.setInterval(() => {
      setCallElapsedSec(Math.max(0, Math.floor((Date.now() - callStartedAtMs) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isCalling, callStartedAtMs]);

  useEffect(() => {
    if (panel === "admin" && adminUnlocked) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [panel, adminUnlocked, adminPage]);

  useEffect(() => {
    if (panel === "admin" && adminUnlocked) {
      const pageTitle = adminPage === "home" ? "Admin Dashboard" : `${tabLabels[adminPage] || "Module"} | Admin`;
      document.title = `${pageTitle} | ${APP_NAME}`;
      return;
    }
    if (panel === "user") {
      document.title = `${APP_NAME} | ${APP_TAGLINE}`;
    }
  }, [panel, adminUnlocked, adminPage]);

  useEffect(() => {
    const onHashChange = () => {
      setAdminPage(parseAdminPageFromHash());
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigateAdminPage = (page) => {
    const target = tabs.includes(page) ? page : "home";
    const nextHash = target === "home" ? "#/admin" : `#/admin/${target}`;
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
    } else {
      setAdminPage(target);
    }
  };

  const startCall = async () => {
    if (!vapiRef.current || !assistantId) {
      setError("Missing Vapi public key or assistant id in frontend/.env");
      return;
    }
    if (isCalling) return;
    setError("");
    setStatus("Connecting to reception…");
    setIsCalling(true);
    const now = Date.now();
    setCallStartedAtMs(now);
    setCallElapsedSec(0);
    if (ringtoneStopRef.current) {
      ringtoneStopRef.current();
      ringtoneStopRef.current = null;
    }
    ringtoneStopRef.current = startConnectingRing();
    try {
      await vapiRef.current.start(assistantId);
    } catch (err) {
      const stop = ringtoneStopRef.current;
      if (stop) {
        stop();
        ringtoneStopRef.current = null;
      }
      setError(`Failed to start call: ${formatVapiError(err)}`);
      setStatus("Idle");
      setIsCalling(false);
      setCallStartedAtMs(null);
      setCallElapsedSec(0);
    }
  };

  const endCall = async () => {
    if (!vapiRef.current) return;
    const stop = ringtoneStopRef.current;
    if (stop) {
      stop();
      ringtoneStopRef.current = null;
    }
    await vapiRef.current.stop();
    setStatus("Idle");
    setIsCalling(false);
    setCallStartedAtMs(null);
    setCallElapsedSec(0);
    setShowPatientDetailsForm(false);
    setDetailsSubmitted(false);
  };

  const createProvider = async () => {
    const parsedFee = String(providerForm.fee_pkr || "").trim();
    await apiRequest("/providers", {
      method: "POST",
      body: JSON.stringify({
        name: providerForm.name,
        service: providerForm.service,
        fee_pkr: parsedFee === "" ? null : Number(parsedFee),
      }),
    });
    setProviderForm({ name: "", service: "", fee_pkr: "" });
    await loadDashboard();
  };

  const createSlot = async () => {
    await apiRequest("/slots", {
      method: "POST",
      body: JSON.stringify({
        provider_id: Number(slotForm.provider_id),
        date: slotForm.date,
        time: slotForm.time,
        end_time: slotForm.end_time,
      }),
    });
    await loadDashboard();
  };

  const createBulkSlots = async () => {
    const times = bulkSlotForm.times.split(",").map((item) => item.trim()).filter(Boolean);
    await apiRequest("/slots/bulk", {
      method: "POST",
      body: JSON.stringify({
        provider_id: Number(bulkSlotForm.provider_id),
        start_date: bulkSlotForm.start_date,
        days: Number(bulkSlotForm.days),
        times,
        duration_minutes: Number(bulkSlotForm.duration_minutes || 30),
      }),
    });
    await loadDashboard();
  };

  const createFaq = async () => {
    await apiRequest("/faqs", {
      method: "POST",
      body: JSON.stringify(faqForm),
    });
    setFaqForm({ question: "", answer: "" });
    await loadDashboard();
  };

  const deleteAppointmentHard = async (appointmentId) => {
    const ok = window.confirm(
      "Are you sure you want to delete this appointment?\n\nIt will be removed from the database and related records updated. This cannot be undone.",
    );
    if (!ok) return;
    await apiRequest(`/appointments/${appointmentId}/hard`, {
      method: "DELETE",
    });
    await loadDashboard();
  };

  const submitAdminCancel = async () => {
    if (cancelModalId == null) return;
    setError("");
    try {
      await apiRequest(`/appointments/${cancelModalId}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason: cancelReason.trim() || undefined }),
      });
      setCancelModalId(null);
      setCancelReason(
        "Emergency — doctor unavailable. You may book another time through our assistant helpline.",
      );
      await loadDashboard();
    } catch (err) {
      setError(`Cancel appointment failed: ${err.message}`);
    }
  };

  const unlockAdmin = async () => {
    if (!adminLogin.username.trim() || !adminLogin.password.trim()) {
      setError("Enter admin username and password.");
      return;
    }
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(adminLogin),
      });
      if (!response.ok) {
        const txt = await response.text();
        throw new Error(txt || "Invalid admin credentials");
      }
      const data = await response.json();
      const token = data.access_token || "";
      if (!token) throw new Error("Token missing in login response.");
      localStorage.setItem("admin_token", token);
      setAdminToken(token);
      setError("");
      setAdminUnlocked(true);
    } catch (err) {
      const msg = err?.message || String(err);
      const loginUrl = apiBase
        ? `${apiBase}/api/v1/auth/login`
        : "/api/v1/auth/login (Vite proxy → :8000)";
      const hint =
        msg === "Failed to fetch"
          ? ` Check: (1) API is running: uvicorn app.main:app --host 127.0.0.1 --port 8000. (2) For local dev, remove VITE_BACKEND_URL from frontend/.env (or leave empty) so requests use the Vite proxy. (3) If you set VITE_BACKEND_URL to a full URL, add your browser address to CORS_ORIGINS in backend .env (e.g. http://192.168.x.x:5173). Tried: ${loginUrl}`
          : "";
      setError(`Admin login failed: ${msg}${hint}`);
    }
  };

  const logoutAdmin = () => {
    localStorage.removeItem("admin_token");
    setAdminToken("");
    setAdminUnlocked(false);
  };

  const deleteProvider = async (providerId) => {
    const ok = window.confirm(
      "Are you sure you want to delete this provider?\n\n" +
        "All slots for this provider will be removed from the database. " +
        "You cannot delete if there are confirmed appointments — cancel those first.\n\n" +
        "This action cannot be undone.",
    );
    if (!ok) return;
    await apiRequest(`/providers/${providerId}/hard`, { method: "DELETE" });
    await loadDashboard();
  };

  const deleteSlot = async (slotId) => {
    await apiRequest(`/slots/${slotId}`, { method: "DELETE" });
    await loadDashboard();
  };

  const deleteFaq = async (faqId) => {
    const ok = window.confirm(
      "Are you sure you want to delete this FAQ?\n\nIt will be removed from the database permanently. This cannot be undone.",
    );
    if (!ok) return;
    await apiRequest(`/faqs/${faqId}`, { method: "DELETE" });
    await loadDashboard();
  };

  const deleteNotificationLog = async (notificationId) => {
    const ok = window.confirm(
      "Delete this notification log entry?\n\nIt will be removed from the database permanently. This cannot be undone.",
    );
    if (!ok) return;
    await apiRequest(`/notifications/${notificationId}`, { method: "DELETE" });
    await loadDashboard();
  };

  const normalizeTime = (t) => {
    if (!t && t !== 0) return "";
    const s = String(t).trim();
    if (s.length === 5 && s.includes(":")) return `${s}:00`;
    return s.length >= 8 ? s.slice(0, 8) : s;
  };

  const saveProviderEdit = async () => {
    if (providerEditId == null) return;
    setError("");
    try {
      await apiRequest(`/providers/${providerEditId}`, {
        method: "PUT",
        body: JSON.stringify({
          name: providerEdit.name.trim(),
          service: providerEdit.service.trim().toLowerCase(),
          fee_pkr: String(providerEdit.fee_pkr || "").trim() === "" ? null : Number(providerEdit.fee_pkr),
          is_active: !!providerEdit.is_active,
        }),
      });
      setProviderEditId(null);
      await loadDashboard();
    } catch (err) {
      setError(`Save provider failed: ${err.message}`);
    }
  };

  const saveSlotEdit = async () => {
    if (slotEditId == null) return;
    setError("");
    try {
      await apiRequest(`/slots/${slotEditId}`, {
        method: "PUT",
        body: JSON.stringify({
          date: slotEdit.date,
          time: normalizeTime(slotEdit.time),
          end_time: normalizeTime(slotEdit.end_time),
        }),
      });
      setSlotEditId(null);
      await loadDashboard();
    } catch (err) {
      setError(`Save slot failed: ${err.message}`);
    }
  };

  const saveFaqEdit = async () => {
    if (faqEditId == null) return;
    setError("");
    try {
      await apiRequest(`/faqs/${faqEditId}`, {
        method: "PUT",
        body: JSON.stringify({
          question: faqEdit.question.trim(),
          answer: faqEdit.answer.trim(),
          is_active: !!faqEdit.is_active,
        }),
      });
      setFaqEditId(null);
      await loadDashboard();
    } catch (err) {
      setError(`Save FAQ failed: ${err.message}`);
    }
  };

  const adminStats = useMemo(() => {
    const totalAppointments = appointments.length;
    const confirmed = appointments.filter((a) => a.status === "confirmed").length;
    const cancelled = appointments.filter((a) => a.status === "cancelled").length;
    const pendingResponses = appointments.filter(
      (a) => a.status === "confirmed" && !(a.patient_response || "").trim(),
    ).length;
    const failedNotifications = notifications.filter((n) => n.status === "failed").length;
    return { totalAppointments, confirmed, cancelled, pendingResponses, failedNotifications };
  }, [appointments, notifications]);

  const isAdminModulePage = panel === "admin" && adminUnlocked && adminPage !== "home";

  return (
    <main className="page">
      <section className="shell">
        {!isAdminModulePage ? (
          <header className="hero hero-clean app-header">
            <div className="app-header-brand">
              <div className="app-logo-wrap" aria-hidden="true" title="Voice helpline">
                <svg className="app-logo-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M3 18v-6a9 9 0 0 1 18 0v6"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div>
                <p className="kicker">{APP_NAME}</p>
                <h1>{APP_TAGLINE}</h1>
                <p className="subtle">Talk to our AI receptionist for bookings, or switch to Admin for staff tools.</p>
              </div>
            </div>
            <div className="actions app-header-tabs">
              <button type="button" className={panel === "user" ? "tab active" : "tab"} onClick={() => setPanel("user")}>
                Patient call
              </button>
              <button type="button" className={panel === "admin" ? "tab active" : "tab"} onClick={() => setPanel("admin")}>
                Staff admin
              </button>
            </div>
          </header>
        ) : null}

        {error ? <p className="error">{error}</p> : null}

        {panel === "user" && (
          <section className="panel user-landing">
            <article className="card user-hero-card">
              <div className="user-hero-inner">
                <div>
                  <h2 className="user-hero-title">Talk to reception</h2>
                  <p className="muted user-hero-desc">
                    Start a live voice session — same as calling the hospital desk. You can book, ask about services, or change an appointment.
                  </p>
                </div>
                <button type="button" className="btn-voice-primary" onClick={startCall} disabled={isCalling}>
                  {isCalling ? "Call in progress…" : "Start voice call"}
                </button>
              </div>
            </article>
            {isCalling ? (
              <div className="voice-call-overlay" role="dialog" aria-modal="true" aria-labelledby="voice-call-title">
                <div className="voice-call-backdrop" />
                <div className="voice-call-content">
                  <p id="voice-call-title" className="voice-call-brand">
                    {APP_NAME}
                  </p>
                  <p className="voice-call-sub">{APP_TAGLINE}</p>
                  <div className="voice-orb-wrap" aria-hidden="true">
                    <span className="voice-orb-ring voice-orb-ring--a" />
                    <span className="voice-orb-ring voice-orb-ring--b" />
                    <span className="voice-orb-ring voice-orb-ring--c" />
                    <div className="voice-orb-core">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                        <path
                          d="M6.62 10.79a15.06 15.06 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.31.56 3.55.56a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.85 21 3 13.15 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.19 2.43.56 3.55a1 1 0 0 1-.24 1.02l-2.2 2.22Z"
                          stroke="currentColor"
                          strokeWidth="1.75"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                  </div>
                  <p className="voice-call-status">{status}</p>
                  <p className="voice-call-timer">Call duration: {callTimerLabel}</p>
                  <button type="button" className="btn-end-call" onClick={endCall}>
                    End call
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        )}

        {panel === "admin" && !adminUnlocked && (
          <section className="panel">
            <article className="card login-card">
              <h3>Admin Login</h3>
              <p className="muted">Temporary UI login gate (backend auth can be enforced later).</p>
              <div className="form-grid">
                <input placeholder="Admin username" value={adminLogin.username} onChange={(e) => setAdminLogin({ ...adminLogin, username: e.target.value })} />
                <input type="password" placeholder="Admin password" value={adminLogin.password} onChange={(e) => setAdminLogin({ ...adminLogin, password: e.target.value })} />
              </div>
              <div className="actions">
                <button onClick={unlockAdmin}>Enter Admin Dashboard</button>
              </div>
            </article>
          </section>
        )}

        {panel === "admin" && adminUnlocked && (
          <>
            <div className="tabs">
              {adminPage !== "home" ? (
                <button className="btn-secondary" onClick={() => navigateAdminPage("home")}>
                  ← Back to modules
                </button>
              ) : null}
              <button className="btn-secondary" onClick={loadDashboard} disabled={loading}>
                {loading ? "Refreshing..." : "Refresh data"}
              </button>
              <button className="btn-secondary" onClick={logoutAdmin}>Logout</button>
            </div>
            {adminPage !== "home" ? (
              <section className="module-header-card">
                <p className="module-kicker">Admin Module</p>
                <h2>{tabLabels[adminPage] || "Module"}</h2>
                <p>{moduleDescriptions[adminPage] || "Manage this section from the admin console."}</p>
              </section>
            ) : null}
            {adminPage === "home" ? (
              <section className="stats-grid">
                <article className="stat-card stat-card--blue">
                  <p className="stat-label">Total appointments</p>
                  <p className="stat-value">{adminStats.totalAppointments}</p>
                </article>
                <article className="stat-card stat-card--green">
                  <p className="stat-label">Confirmed</p>
                  <p className="stat-value">{adminStats.confirmed}</p>
                </article>
                <article className="stat-card stat-card--amber">
                  <p className="stat-label">Awaiting response</p>
                  <p className="stat-value">{adminStats.pendingResponses}</p>
                </article>
                <article className="stat-card stat-card--red">
                  <p className="stat-label">Cancelled</p>
                  <p className="stat-value">{adminStats.cancelled}</p>
                </article>
                <article className="stat-card stat-card--violet">
                  <p className="stat-label">Failed notifications</p>
                  <p className="stat-value">{adminStats.failedNotifications}</p>
                </article>
              </section>
            ) : null}

            {adminPage === "home" && (
              <section className="panel">
                <article className="card">
                  <h3>Admin Modules</h3>
                  <p className="muted">Open one section at a time for a cleaner workflow.</p>
                  <div className="module-grid">
                    {tabs.map((tab) => (
                      <button
                        key={tab}
                        type="button"
                        className="module-card"
                        onClick={() => navigateAdminPage(tab)}
                      >
                        <span className="module-title">{tabLabels[tab] || tab}</span>
                        <span className="module-subtitle">Open section</span>
                      </button>
                    ))}
                  </div>
                </article>
              </section>
            )}

            {adminPage === "providers" && (
              <section className="panel">
                <article className="card">
                  <h3>Create Provider</h3>
                  <div className="form-grid">
                    <input placeholder="Name" value={providerForm.name} onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })} />
                    <input placeholder="Service (general/dentist/dermatologist)" value={providerForm.service} onChange={(e) => setProviderForm({ ...providerForm, service: e.target.value })} />
                    <input placeholder="Fee PKR (e.g. 2500)" type="number" min="0" value={providerForm.fee_pkr} onChange={(e) => setProviderForm({ ...providerForm, fee_pkr: e.target.value })} />
                  </div>
                  <div className="actions">
                    <button onClick={createProvider}>Add Provider</button>
                  </div>
                </article>
                <article className="card">
                  <h3>Providers</h3>
                  <p className="muted">Edit name, service, or active status — changes save to the database.</p>
                  <TableProvider
                    providers={providers}
                    onDelete={deleteProvider}
                    editingId={providerEditId}
                    edit={providerEdit}
                    onEditChange={setProviderEdit}
                    onStartEdit={(p) => {
                      setProviderEditId(p.id);
                      setProviderEdit({ name: p.name, service: p.service, fee_pkr: p.fee_pkr ?? "", is_active: !!p.is_active });
                    }}
                    onCancelEdit={() => setProviderEditId(null)}
                    onSaveEdit={saveProviderEdit}
                  />
                </article>
              </section>
            )}

            {adminPage === "slots" && (
              <section className="panel">
                <article className="card">
                  <h3>Create Single Slot</h3>
                  <div className="form-grid">
                    <input placeholder="Provider ID" value={slotForm.provider_id} onChange={(e) => setSlotForm({ ...slotForm, provider_id: e.target.value })} />
                    <input type="date" value={slotForm.date} onChange={(e) => setSlotForm({ ...slotForm, date: e.target.value })} />
                    <input type="time" step="1" value={slotForm.time} onChange={(e) => setSlotForm({ ...slotForm, time: e.target.value })} />
                    <input type="time" step="1" value={slotForm.end_time} onChange={(e) => setSlotForm({ ...slotForm, end_time: e.target.value })} />
                  </div>
                  <div className="actions">
                    <button onClick={createSlot}>Create Slot</button>
                  </div>
                </article>
                <article className="card">
                  <h3>Bulk Slot Generator</h3>
                  <div className="form-grid">
                    <input placeholder="Provider ID" value={bulkSlotForm.provider_id} onChange={(e) => setBulkSlotForm({ ...bulkSlotForm, provider_id: e.target.value })} />
                    <input type="date" value={bulkSlotForm.start_date} onChange={(e) => setBulkSlotForm({ ...bulkSlotForm, start_date: e.target.value })} />
                    <input placeholder="Days" value={bulkSlotForm.days} onChange={(e) => setBulkSlotForm({ ...bulkSlotForm, days: e.target.value })} />
                    <input placeholder="Times CSV e.g. 10:00,12:00,15:00" value={bulkSlotForm.times} onChange={(e) => setBulkSlotForm({ ...bulkSlotForm, times: e.target.value })} />
                    <input placeholder="Duration minutes (e.g. 30)" value={bulkSlotForm.duration_minutes} onChange={(e) => setBulkSlotForm({ ...bulkSlotForm, duration_minutes: e.target.value })} />
                  </div>
                  <div className="actions">
                    <button onClick={createBulkSlots}>Create Bulk Slots</button>
                  </div>
                </article>
                <article className="card">
                  <h3>Slots</h3>
                  <p className="muted">Only unbooked slots can be edited (date / start / end).</p>
                  <TableSlots
                    slots={slots}
                    onDelete={deleteSlot}
                    editingId={slotEditId}
                    edit={slotEdit}
                    onEditChange={setSlotEdit}
                    onStartEdit={(s) => {
                      setSlotEditId(s.id);
                      setSlotEdit({
                        date: String(s.date || "").slice(0, 10),
                        time: normalizeTime(s.time),
                        end_time: normalizeTime(s.end_time || s.time),
                      });
                    }}
                    onCancelEdit={() => setSlotEditId(null)}
                    onSaveEdit={saveSlotEdit}
                  />
                </article>
              </section>
            )}

            {adminPage === "appointments" && (
              <section className="panel">
                <article className="card">
                  <h3>Appointments</h3>
                  <p className="muted">
                    <strong>Cancel</strong> notifies the patient by SMS, removes the calendar event, and frees the slot.
                    <strong> Remove record</strong> permanently deletes the row (use only when needed).
                  </p>
                  <TableAppointments
                    appointments={appointments}
                    onRequestCancel={(id) => setCancelModalId(id)}
                    onHardDelete={deleteAppointmentHard}
                  />
                </article>
              </section>
            )}

            {adminPage === "faqs" && (
              <section className="panel">
                <article className="card">
                  <h3>Create FAQ</h3>
                  <div className="form-grid">
                    <input placeholder="Question" value={faqForm.question} onChange={(e) => setFaqForm({ ...faqForm, question: e.target.value })} />
                    <input placeholder="Answer" value={faqForm.answer} onChange={(e) => setFaqForm({ ...faqForm, answer: e.target.value })} />
                  </div>
                  <div className="actions">
                    <button onClick={createFaq}>Add FAQ</button>
                  </div>
                </article>
                <article className="card">
                  <h3>FAQs</h3>
                  <TableFaqs
                    faqs={faqs}
                    onDelete={deleteFaq}
                    editingId={faqEditId}
                    edit={faqEdit}
                    onEditChange={setFaqEdit}
                    onStartEdit={(f) => {
                      setFaqEditId(f.id);
                      setFaqEdit({ question: f.question, answer: f.answer, is_active: !!f.is_active });
                    }}
                    onCancelEdit={() => setFaqEditId(null)}
                    onSaveEdit={saveFaqEdit}
                  />
                </article>
              </section>
            )}

            {adminPage === "notifications" && (
              <section className="panel">
                <article className="card">
                  <h3>Notification Logs</h3>
                  <TableNotifications rows={notifications} onDelete={deleteNotificationLog} />
                </article>
              </section>
            )}
          </>
        )}

        {adminUnlocked && cancelModalId != null ? (
          <div
            className="admin-modal-backdrop"
            role="presentation"
            onClick={() => setCancelModalId(null)}
          >
            <div
              className="admin-modal"
              role="dialog"
              aria-labelledby="cancel-modal-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 id="cancel-modal-title">Cancel appointment #{cancelModalId}</h3>
              <p className="muted">
                Message below is sent to the patient by SMS. Use the phone number from booking.
              </p>
              <label className="admin-modal-label" htmlFor="cancel-reason">
                Reason for patient
              </label>
              <textarea
                id="cancel-reason"
                className="admin-modal-textarea"
                rows={4}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Doctor emergency — please book another slot via our assistant."
              />
              <div className="admin-modal-actions">
                <button type="button" className="btn-cancel-confirm" onClick={submitAdminCancel}>
                  Confirm cancel
                </button>
                <button type="button" className="btn-secondary" onClick={() => setCancelModalId(null)}>
                  Close
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function TableProvider({ providers, onDelete, editingId, edit, onEditChange, onStartEdit, onCancelEdit, onSaveEdit }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>Name</th><th>Service</th><th>Fee PKR</th><th>Active</th><th>Confirmed</th><th>Actions</th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id}>
              <td>{p.id}</td>
              {editingId === p.id ? (
                <>
                  <td><input value={edit.name} onChange={(e) => onEditChange({ ...edit, name: e.target.value })} /></td>
                  <td><input value={edit.service} onChange={(e) => onEditChange({ ...edit, service: e.target.value })} /></td>
                  <td><input type="number" min="0" value={edit.fee_pkr} onChange={(e) => onEditChange({ ...edit, fee_pkr: e.target.value })} /></td>
                  <td>
                    <label className="inline-check">
                      <input type="checkbox" checked={edit.is_active} onChange={(e) => onEditChange({ ...edit, is_active: e.target.checked })} /> active
                    </label>
                  </td>
                </>
              ) : (
                <>
                  <td>{p.name}</td><td>{p.service}</td><td>{p.fee_pkr == null ? "—" : `PKR ${p.fee_pkr}`}</td><td>{String(p.is_active)}</td>
                </>
              )}
              <td>{p.active_appointments_count}</td>
              <td className="actions">
                {editingId === p.id ? (
                  <>
                    <button type="button" onClick={onSaveEdit}>Save</button>
                    <button type="button" className="btn-secondary" onClick={onCancelEdit}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn-secondary" onClick={() => onStartEdit(p)}>Edit</button>
                    <button type="button" className="btn-secondary" onClick={() => onDelete(p.id)}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableSlots({ slots, onDelete, editingId, edit, onEditChange, onStartEdit, onCancelEdit, onSaveEdit }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>Provider</th><th>Date</th><th>Start</th><th>End</th><th>Booked</th><th>Actions</th></tr></thead>
        <tbody>
          {slots.map((s) => (
            <tr key={s.id}>
              <td>{s.id}</td>
              <td>{s.provider_id}</td>
              {editingId === s.id ? (
                <>
                  <td><input type="date" value={edit.date} onChange={(e) => onEditChange({ ...edit, date: e.target.value })} /></td>
                  <td><input type="time" step="1" value={edit.time} onChange={(e) => onEditChange({ ...edit, time: e.target.value })} /></td>
                  <td><input type="time" step="1" value={edit.end_time} onChange={(e) => onEditChange({ ...edit, end_time: e.target.value })} /></td>
                </>
              ) : (
                <>
                  <td>{s.date}</td><td>{formatDisplayTime(s.time)}</td><td>{formatDisplayTime(s.end_time)}</td>
                </>
              )}
              <td>{String(s.is_booked)}</td>
              <td className="actions">
                {editingId === s.id ? (
                  <>
                    <button type="button" onClick={onSaveEdit}>Save</button>
                    <button type="button" className="btn-secondary" onClick={onCancelEdit}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn-secondary" disabled={s.is_booked} onClick={() => onStartEdit(s)}>Edit</button>
                    <button type="button" className="btn-secondary" disabled={s.is_booked} onClick={() => onDelete(s.id)}>delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableAppointments({ appointments, onRequestCancel, onHardDelete }) {
  const dueText = (targetMs, nowMs = Date.now()) => {
    const diffMin = Math.floor((targetMs - nowMs) / 60000);
    if (diffMin < 0) return "overdue";
    if (diffMin === 0) return "due now";
    return `due in ${diffMin} min`;
  };

  const reminderStatusText = (a) => {
    if (!a || a.status !== "confirmed") {
      return {
        sms: "—",
        whatsapp: "—",
      };
    }

    const dateText = String(a.date || "").slice(0, 10);
    const timeText = String(a.time || "").slice(0, 8);
    if (!dateText || !timeText) {
      return {
        sms: "—",
        whatsapp: "—",
      };
    }

    const apptAt = new Date(`${dateText}T${timeText}`);
    if (Number.isNaN(apptAt.getTime())) {
      return {
        sms: "—",
        whatsapp: "—",
      };
    }

    const nowMs = Date.now();
    const smsAtMs = apptAt.getTime() - (24 * 60 * 60 * 1000);
    const whatsappAtMs = apptAt.getTime() - (24 * 60 * 60 * 1000);
    let sms = "pending";
    if (a.reminder_sent_at) sms = "sent";
    else sms = dueText(smsAtMs, nowMs);

    let whatsapp = "pending";
    if ((a.patient_response || "").trim()) whatsapp = "skipped (responded)";
    else if (a.reminder_whatsapp_sent_at) whatsapp = "sent";
    else whatsapp = dueText(whatsappAtMs, nowMs);

    return {
      sms,
      whatsapp,
    };
  };

  const chipTone = (value) => {
    const text = String(value || "").toLowerCase();
    if (text.includes("sent") || text.includes("confirmed") || text.includes("yes")) return "success";
    if (text.includes("overdue") || text.includes("failed") || text.includes("cancel")) return "danger";
    if (text.includes("due now") || text.includes("pending")) return "warning";
    if (text.includes("skip")) return "muted";
    return "info";
  };

  const compactTone = (value) => {
    const text = String(value || "").toLowerCase();
    if (text.includes("sent") || text.includes("confirmed") || text.includes("yes")) return "ok";
    if (text.includes("overdue") || text.includes("failed") || text.includes("cancel")) return "bad";
    if (text.includes("due now") || text.includes("pending")) return "warn";
    if (text.includes("skip")) return "muted";
    return "info";
  };

  return (
    <div className="table-wrap appt-table-wrap">
      <table className="appt-admin-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Patient</th>
            <th>Phone</th>
            <th>Provider</th>
            <th>Service</th>
            <th>Date</th>
            <th>Start</th>
            <th>End</th>
            <th>Status</th>
            <th>Reminder Alert</th>
            <th>Patient Reply</th>
            <th className="appt-col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((a) => (
            <tr key={a.id}>
              <td>{a.id}</td>
              <td>{a.user_name}</td>
              <td>{a.user_phone || "—"}</td>
              <td>{a.provider_name}</td>
              <td>{a.service}</td>
              <td>{a.date}</td>
              <td>{formatDisplayTime(a.time)}</td>
              <td>{formatDisplayTime(a.end_time)}</td>
              <td>
                <span className={`status-pill status-pill--${chipTone(a.status)}`}>{a.status}</span>
              </td>
              <td>
                {(() => {
                  const status = reminderStatusText(a);
                  return (
                    <div className="reminder-inline-list">
                      <p className="reminder-inline-item">
                        <span className={`tone-dot tone-dot--${compactTone(status.sms)}`} />
                        <span className="reminder-inline-label">SMS</span>
                        <span className="reminder-inline-value">{status.sms}</span>
                      </p>
                      <p className="reminder-inline-item">
                        <span className={`tone-dot tone-dot--${compactTone(status.whatsapp)}`} />
                        <span className="reminder-inline-label">WhatsApp</span>
                        <span className="reminder-inline-value">{status.whatsapp}</span>
                      </p>
                    </div>
                  );
                })()}
              </td>
              <td>
                <span className={`status-pill status-pill--${chipTone(a.patient_response || "pending")}`}>
                  {a.patient_response || "pending"}
                </span>
              </td>
              <td className="appt-actions-cell">
                <div className="appt-row-actions">
                  {a.status === "confirmed" ? (
                    <button type="button" className="btn-cancel-appt" onClick={() => onRequestCancel(a.id)}>
                      Cancel
                    </button>
                  ) : null}
                  <button type="button" className="btn-secondary btn-compact" onClick={() => onHardDelete(a.id)}>
                    Remove
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableFaqs({ faqs, onDelete, editingId, edit, onEditChange, onStartEdit, onCancelEdit, onSaveEdit }) {
  return (
    <div className="table-wrap faq-table-wrap">
      <table className="faq-admin-table">
        <thead>
          <tr>
            <th className="faq-col-id">ID</th>
            <th>Question</th>
            <th>Answer</th>
            <th className="faq-col-active">Active</th>
            <th className="faq-col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {faqs.map((f) => (
            <tr key={f.id}>
              <td>{f.id}</td>
              {editingId === f.id ? (
                <>
                  <td>
                    <input
                      className="faq-input-question"
                      value={edit.question}
                      onChange={(e) => onEditChange({ ...edit, question: e.target.value })}
                    />
                  </td>
                  <td>
                    <textarea
                      className="faq-textarea-answer"
                      value={edit.answer}
                      onChange={(e) => onEditChange({ ...edit, answer: e.target.value })}
                      rows={2}
                    />
                  </td>
                  <td>
                    <label className="inline-check">
                      <input type="checkbox" checked={edit.is_active} onChange={(e) => onEditChange({ ...edit, is_active: e.target.checked })} /> active
                    </label>
                  </td>
                </>
              ) : (
                <>
                  <td className="faq-cell-text">{f.question}</td>
                  <td className="faq-cell-text">{f.answer}</td>
                  <td>{String(f.is_active)}</td>
                </>
              )}
              <td className="faq-actions-cell">
                <div className="faq-row-actions">
                  {editingId === f.id ? (
                    <>
                      <button type="button" onClick={onSaveEdit}>Save</button>
                      <button type="button" className="btn-secondary" onClick={onCancelEdit}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn-secondary btn-compact" onClick={() => onStartEdit(f)}>Edit</button>
                      <button type="button" className="btn-secondary btn-compact" onClick={() => onDelete(f.id)}>Delete</button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function notificationEventLabel(eventType) {
  if (!eventType) return "—";
  const map = {
    booked: "Booking confirmation",
    cancelled: "Cancellation",
    rescheduled: "Reschedule",
    reminder: "1h reminder",
  };
  return map[eventType] || eventType;
}

function TableNotifications({ rows, onDelete }) {
  const chipTone = (value) => {
    const text = String(value || "").toLowerCase();
    if (text.includes("sent") || text.includes("success")) return "success";
    if (text.includes("fail") || text.includes("error")) return "danger";
    if (text.includes("pending") || text.includes("queued")) return "warning";
    return "info";
  };

  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>Event</th><th>Appointment</th><th>Channel</th><th>Recipient</th><th>Status</th><th>Error</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{notificationEventLabel(r.event_type)}</td>
              <td>{r.appointment_id}</td>
              <td><span className={`status-pill status-pill--${chipTone(r.channel)}`}>{r.channel}</span></td>
              <td>{r.recipient}</td>
              <td><span className={`status-pill status-pill--${chipTone(r.status)}`}>{r.status}</span></td>
              <td>{r.error ? <span className="error-inline">{r.error}</span> : "-"}</td>
              <td className="actions">
                <button className="btn-secondary" onClick={() => onDelete(r.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
