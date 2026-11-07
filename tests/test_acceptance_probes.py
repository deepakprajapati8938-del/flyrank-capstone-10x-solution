import json
import time
import pytest
import pydantic
from fastapi import HTTPException

from app.config import DATABASE_PATH
from app.database import init_db, get_db
from app.models import (
    UserRegisterRequest, UserLoginRequest, IncidentIngestRequest,
    IncidentTriageAnalysis, MitigationStep
)
from app.auth import (
    hash_password, verify_password, create_access_token,
    verify_access_token, get_current_user, require_admin
)
from app.cache import compute_error_signature, get_cached_triage, set_cached_triage
from app.llm_triage import analyze_incident_with_llm, get_cost_summary, record_ai_cost
from app.reporting import generate_incident_report
from app.jobs import process_incident_queue
from app.main import (
    read_root, health_check, register_user, login,
    ingest_incident_alert, list_incidents, get_incident,
    trigger_triage_worker, get_report_json, get_report_html, get_ai_costs
)
from seed import seed_database

@pytest.fixture(autouse=True)
def reset_database_state():
    """Ensure clean schema and fresh seed data before each test."""
    init_db(DATABASE_PATH)
    seed_database(DATABASE_PATH)
    yield

# -------------------------------------------------------------
# Concept 1: API Endpoints & Boundary Validation
# -------------------------------------------------------------
def test_concept_1_api_and_boundary_validation():
    """Validates FastAPI routing handlers, 202 Accepted status, and Pydantic boundary validation."""
    # 1. Root & Health Check handlers
    root = read_root()
    assert root["service"] == "IncidentPulse Engine"
    assert "10x_claim" in root
    assert "auth_login" in root["endpoints"]

    health = health_check()
    assert health["status"] == "healthy"
    assert health["database"] == "connected"

    # 2. Pydantic Boundary Validation on Input Schemas
    valid_req = IncidentIngestRequest(
        service_name="payment-service",
        error_message="ConnectionPoolTimeoutException: Database pool exhausted",
        stack_trace="HikariPool.getConnection(HikariPool.java:186)",
        severity="critical"
    )
    assert valid_req.service_name == "payment-service"

    # Reject empty service_name (min_length=1)
    with pytest.raises(pydantic.ValidationError):
        IncidentIngestRequest(
            service_name="",
            error_message="Some error"
        )

    # Reject missing required error_message
    with pytest.raises(pydantic.ValidationError):
        IncidentIngestRequest(
            service_name="payment-service"
        )

    # 3. Alert Ingestion handler (<15ms response path)
    user_context = {"id": "usr_eng_002", "email": "engineer@company.com", "role": "engineer"}
    t0 = time.time()
    res = ingest_incident_alert(valid_req, user=user_context)
    elapsed_ms = (time.time() - t0) * 1000

    assert res["status"] == "accepted"
    assert res["incident_id"].startswith("inc_")
    assert res["enqueued_by"] == "engineer@company.com"
    assert elapsed_ms < 500, f"Ingestion took {elapsed_ms:.2f}ms, expected < 500ms"

# -------------------------------------------------------------
# Concept 2: Database Persistence & Storage
# -------------------------------------------------------------
def test_concept_2_database_persistence():
    """Validates SQLite schema integrity, tables creation, WAL mode, and persistent records."""
    with get_db(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Check WAL mode is enabled
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0].lower()
        assert mode in ["wal", "memory"], f"Expected WAL mode, got {mode}"

        # Verify all 6 required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        assert "users" in tables
        assert "incidents" in tables
        assert "runbooks" in tables
        assert "triage_cache" in tables
        assert "ai_cost_logs" in tables
        assert "incident_reports" in tables

        # Verify seeded runbooks persist
        cursor.execute("SELECT count(*) FROM runbooks")
        assert cursor.fetchone()[0] >= 3

        # Verify seeded users persist
        cursor.execute("SELECT email, role FROM users WHERE email = ?", ("admin@company.com",))
        admin = cursor.fetchone()
        assert admin is not None
        assert admin["role"] == "admin"

        # Verify seeded incidents persist
        cursor.execute("SELECT count(*) FROM incidents WHERE status = 'pending_triage'")
        assert cursor.fetchone()[0] >= 2

# -------------------------------------------------------------
# Concept 3: JWT Authentication & RBAC Access Control
# -------------------------------------------------------------
def test_concept_3_jwt_authentication_and_rbac():
    """Validates salted PBKDF2 hashing, JWT verification, and Role-Based Access Control."""
    # 1. Salted PBKDF2 Hashing & Verification
    raw_pwd = "SecurePassword123!"
    hashed = hash_password(raw_pwd)
    assert hashed != raw_pwd
    assert "$" in hashed
    assert verify_password(raw_pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

    # 2. User Registration
    new_reg = UserRegisterRequest(email="new_dev@company.com", password="SecretPassword99!", role="engineer")
    created = register_user(new_reg)
    assert created.email == "new_dev@company.com"
    assert created.role == "engineer"

    # Reject duplicate email registration
    with pytest.raises(HTTPException) as exc:
        register_user(new_reg)
    assert exc.value.status_code == 400

    # 3. User Login & JWT Generation
    login_req = UserLoginRequest(email="engineer@company.com", password="engineerpassword123")
    token_resp = login(login_req)
    assert token_resp.token_type == "bearer"
    assert token_resp.access_token is not None

    # Invalid login credentials rejection
    with pytest.raises(HTTPException) as exc_login:
        login(UserLoginRequest(email="engineer@company.com", password="IncorrectPassword"))
    assert exc_login.value.status_code == 401

    # 4. Token Claims Verification
    decoded_claims = verify_access_token(token_resp.access_token)
    assert decoded_claims["email"] == "engineer@company.com"
    assert decoded_claims["role"] == "engineer"

    # 5. Role-Based Access Control (RBAC)
    engineer_user = {"id": "usr_eng_002", "email": "engineer@company.com", "role": "engineer"}
    admin_user = {"id": "usr_admin_001", "email": "admin@company.com", "role": "admin"}

    # Engineer cannot access admin endpoint -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_rbac:
        require_admin(engineer_user)
    assert exc_rbac.value.status_code == 403

    # Admin access granted
    admin_passed = require_admin(admin_user)
    assert admin_passed["role"] == "admin"

# -------------------------------------------------------------
# Concept 4: Background Jobs & Queue Worker
# -------------------------------------------------------------
def test_concept_4_background_jobs_queue():
    """Validates asynchronous triage worker queue processing off the HTTP path."""
    user_context = {"id": "usr_eng_002", "email": "engineer@company.com", "role": "engineer"}

    # Ingest a fresh pending incident
    ing = ingest_incident_alert(IncidentIngestRequest(
        service_name="payment-service",
        error_message="ConnectionPoolTimeoutException: Timeout waiting for idle connection",
        stack_trace="com.zaxxer.hikari.pool.HikariPool.getConnection()",
        severity="critical"
    ), user=user_context)
    inc_id = ing["incident_id"]

    # Trigger background triage worker
    worker_res = trigger_triage_worker(batch_size=10, user=user_context)
    assert worker_res["status"] == "completed"
    results = worker_res["worker_results"]
    assert results["processed_count"] >= 1
    assert results["reports_generated"] >= 1

    # Verify incident state changed from pending_triage -> triaged in database
    detail = get_incident(inc_id, user=user_context)
    assert detail["status"] == "triaged"
    assert detail["root_cause"] is not None
    assert len(detail["root_cause"]) > 10

# -------------------------------------------------------------
# Concept 5: Automated Executive Reporting
# -------------------------------------------------------------
def test_concept_5_executive_report_generation():
    """Validates generation of executive post-mortem HTML and structured JSON reports."""
    user_context = {"id": "usr_eng_002", "email": "engineer@company.com", "role": "engineer"}

    # Ingest and triage an incident
    ing = ingest_incident_alert(IncidentIngestRequest(
        service_name="search-service",
        error_message="OutOfMemoryError: Java heap space",
        stack_trace="java.lang.OutOfMemoryError: Java heap space in Elasticsearch indexer",
        severity="critical"
    ), user=user_context)
    inc_id = ing["incident_id"]
    trigger_triage_worker(batch_size=10, user=user_context)

    # 1. Fetch structured post-mortem JSON
    report_json = get_report_json(inc_id, user=user_context)
    assert report_json["incident_id"] == inc_id
    assert report_json["mttr_minutes"] >= 1
    assert len(report_json["mitigation_steps"]) >= 1

    # 2. Fetch standalone styled HTML report
    report_html_resp = get_report_html(inc_id)
    html_text = report_html_resp.body.decode("utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "Executive Incident Post-Mortem" in html_text
    assert "search-service" in html_text
    assert "Immediate Remediation & Preventative Action Items" in html_text
    assert "Calculated MTTR" in html_text

# -------------------------------------------------------------
# Concept 6: Deterministic Signature TTL Caching
# -------------------------------------------------------------
def test_concept_6_ttl_cache_signature_hit():
    """Validates deterministic error signature hashing and cache hit logic with 0 AI cost."""
    user_context = {"id": "usr_eng_002", "email": "engineer@company.com", "role": "engineer"}
    svc = "auth-service"
    msg = "ExpiredSignatureError: Auth token signature has drifted beyond tolerance"
    st = "jwt.exceptions.ExpiredSignatureError at auth.py:48"

    # 1. Deterministic Hash Property
    sig1 = compute_error_signature(svc, msg, st)
    sig2 = compute_error_signature(svc, msg, st)
    assert sig1 == sig2
    assert len(sig1) == 64

    # 2. First Ingestion -> Cache Miss -> AI Triage -> Caches Diagnosis
    ing1 = ingest_incident_alert(IncidentIngestRequest(
        service_name=svc, error_message=msg, stack_trace=st, severity="high"
    ), user=user_context)
    w1 = trigger_triage_worker(batch_size=10, user=user_context)["worker_results"]
    assert w1["cache_misses"] >= 1

    # 3. Second Ingestion with identical error -> Cache Hit -> $0 AI compute
    ing2 = ingest_incident_alert(IncidentIngestRequest(
        service_name=svc, error_message=msg, stack_trace=st, severity="high"
    ), user=user_context)
    w2 = trigger_triage_worker(batch_size=10, user=user_context)["worker_results"]
    assert w2["cache_hits"] >= 1
    hit_details = [d for d in w2["details"] if d["cached"] is True]
    assert len(hit_details) >= 1

    # 4. Verify cached entry is present in SQLite triage_cache table
    cached_entry = get_cached_triage(sig1, DATABASE_PATH)
    assert cached_entry is not None
    assert "root_cause_hypothesis" in cached_entry

# -------------------------------------------------------------
# Concept 7: Narrow LLM Integration & Cost Tracking
# -------------------------------------------------------------
def test_concept_7_llm_triage_and_cost_logging():
    """Validates structured LLM root-cause synthesis, schema verification, and per-call cost logs."""
    admin_user = {"id": "usr_admin_001", "email": "admin@company.com", "role": "admin"}

    # 1. Direct LLM Triage Execution
    analysis = analyze_incident_with_llm(
        service_name="payment-service",
        error_message="ConnectionPoolTimeoutException: Pool exhausted",
        stack_trace="HikariPool.java:186",
        runbooks=[{
            "id": "rb_test_01",
            "service_name": "payment-service",
            "title": "Payment Pool Runbook",
            "error_pattern": "ConnectionPoolTimeoutException",
            "remediation_steps": json.dumps([{"action": "Restart worker pods", "command_or_fix": "kubectl rollout restart"}])
        }],
        db_path=DATABASE_PATH
    )

    # Verify Pydantic schema validation
    assert isinstance(analysis, IncidentTriageAnalysis)
    assert analysis.matched_runbook_id == "rb_test_01"
    assert len(analysis.mitigation_steps) >= 1
    assert analysis.confidence_score >= 0.90

    # 2. Cost Logging Audit
    cost_summary = get_ai_costs(user=admin_user)
    assert cost_summary["total_calls"] >= 1
    assert cost_summary["total_cost_usd"] > 0.0
    assert "incident_root_cause_triage" in cost_summary["by_operation"]
    assert len(cost_summary["recent_logs"]) >= 1

    latest_log = cost_summary["recent_logs"][0]
    assert latest_log["operation"] == "incident_root_cause_triage"
    assert latest_log["cost_usd"] > 0.0
    assert latest_log["input_units"] > 0
    assert latest_log["output_units"] > 0
