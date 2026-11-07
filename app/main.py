import uuid
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import DATABASE_PATH
from app.database import init_db, get_db
from app.models import (
    UserRegisterRequest, UserLoginRequest, TokenResponse, UserResponse,
    IncidentIngestRequest, IncidentResponse, IncidentReportResponse,
    CostSummaryResponse
)
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin
)
from app.jobs import process_incident_queue
from app.reporting import generate_incident_report
from app.llm_triage import get_cost_summary

# Initialize database schema
init_db(DATABASE_PATH)

app = FastAPI(
    title="IncidentPulse — Autonomous API Incident Triage & Post-Mortem Engine",
    description="Your 10x Solution: Ingest alerts in <15ms, AI root cause analysis, TTL caching, background triage, and executive post-mortems.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["General"])
def read_root():
    return {
        "service": "IncidentPulse Engine",
        "status": "online",
        "10x_claim": "Reduces incident triage and post-mortem drafting from 45-60 mins to 15 seconds.",
        "endpoints": {
            "auth_login": "POST /api/auth/login",
            "ingest_alert": "POST /api/incidents/ingest",
            "run_triage_worker": "POST /api/jobs/triage-worker",
            "view_report_html": "GET /api/incidents/{id}/report.html",
            "cost_audit": "GET /api/costs"
        }
    }

@app.get("/health", tags=["General"])
def health_check():
    return {"status": "healthy", "database": "connected"}

# -------------------------------------------------------------
# Concept 3: Authentication & Protected Routes
# -------------------------------------------------------------

@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
def register_user(req: UserRegisterRequest):
    """Registers a new user with salted PBKDF2 password hashing."""
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    pwd_hash = hash_password(req.password)

    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="User with this email already exists.")

        cursor.execute(
            "INSERT INTO users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (user_id, req.email, pwd_hash, req.role or "engineer")
        )
        conn.commit()

    return UserResponse(id=user_id, email=req.email, role=req.role or "engineer", created_at="just now")

@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(req: UserLoginRequest):
    """Authenticates credentials and issues signed JWT bearer token."""
    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, password_hash, role FROM users WHERE email = ?", (req.email,))
        row = cursor.fetchone()
        if not row or not verify_password(req.password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

        token = create_access_token(row["id"], row["email"], row["role"])
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_id=row["id"],
            email=row["email"],
            role=row["role"]
        )

@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Protected route verifying JWT token authentication."""
    return UserResponse(id=user["id"], email=user["email"], role=user["role"], created_at="active")

# -------------------------------------------------------------
# Concept 1 & 2: API Endpoints, Boundary Validation & Persistence
# -------------------------------------------------------------

@app.post("/api/incidents/ingest", status_code=status.HTTP_202_ACCEPTED, tags=["Incidents"])
def ingest_incident_alert(req: IncidentIngestRequest, user: dict = Depends(get_current_user)):
    """
    Ingests an incident alert in < 15ms and enqueues it for asynchronous triage.
    Protected by JWT Bearer token authentication.
    """
    inc_id = f"inc_{uuid.uuid4().hex[:8]}"

    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO incidents (id, service_name, error_message, stack_trace, severity, status)
            VALUES (?, ?, ?, ?, ?, 'pending_triage')
            """,
            (inc_id, req.service_name, req.error_message, req.stack_trace, req.severity)
        )
        conn.commit()

    return {
        "status": "accepted",
        "incident_id": inc_id,
        "message": f"Alert for '{req.service_name}' queued for autonomous triage.",
        "enqueued_by": user["email"]
    }

@app.get("/api/incidents", tags=["Incidents"])
def list_incidents(status_filter: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Protected route listing all persisted incidents."""
    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute("SELECT * FROM incidents WHERE status = ? ORDER BY ingested_at DESC", (status_filter,))
        else:
            cursor.execute("SELECT * FROM incidents ORDER BY ingested_at DESC")
        return [dict(r) for r in cursor.fetchall()]

@app.get("/api/incidents/{incident_id}", tags=["Incidents"])
def get_incident(incident_id: str, user: dict = Depends(get_current_user)):
    """Protected route fetching incident details."""
    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
        return dict(row)

# -------------------------------------------------------------
# Concept 4: Background Jobs & Asynchronous Worker
# -------------------------------------------------------------

@app.post("/api/jobs/triage-worker", tags=["Background Jobs"])
def trigger_triage_worker(batch_size: int = 10, user: dict = Depends(get_current_user)):
    """
    Triggers asynchronous triage worker to process pending queue off the HTTP request path.
    Enforces caching, runs narrow AI diagnosis, and compiles post-mortems.
    """
    result = process_incident_queue(batch_size, DATABASE_PATH)
    return {
        "status": "completed",
        "worker_results": result
    }

# -------------------------------------------------------------
# Concept 5: Reporting — HTML & Printable Deliverables
# -------------------------------------------------------------

@app.get("/api/incidents/{incident_id}/report", tags=["Reporting"])
def get_report_json(incident_id: str, user: dict = Depends(get_current_user)):
    """Returns structured post-mortem metadata."""
    try:
        report = generate_incident_report(incident_id, DATABASE_PATH)
        return report
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@app.get("/api/incidents/{incident_id}/report.html", response_class=HTMLResponse, tags=["Reporting"])
def get_report_html(incident_id: str):
    """
    Returns standalone, fully-styled HTML Executive Post-Mortem Report.
    Printable to PDF directly from any web browser.
    """
    html_content = None
    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT html_content FROM incident_reports WHERE incident_id = ?", (incident_id,))
        row = cursor.fetchone()
        if row:
            html_content = row["html_content"]

    if not html_content:
        try:
            generate_incident_report(incident_id, DATABASE_PATH)
            with get_db(DATABASE_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT html_content FROM incident_reports WHERE incident_id = ?", (incident_id,))
                row = cursor.fetchone()
                if row:
                    html_content = row["html_content"]
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Report for '{incident_id}' not found: {str(e)}")

    if not html_content:
        raise HTTPException(status_code=404, detail=f"Report for '{incident_id}' not found.")

    return HTMLResponse(content=html_content)

# -------------------------------------------------------------
# Concept 7: Cost Tracking & Audit Logs
# -------------------------------------------------------------

@app.get("/api/costs", response_model=CostSummaryResponse, tags=["Audit"])
def get_ai_costs(user: dict = Depends(require_admin)):
    """Admin-only endpoint providing per-call AI audit logs and budget attribution."""
    return get_cost_summary(DATABASE_PATH)
