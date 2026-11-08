import json
import datetime
from typing import Dict, Any, List
from app.config import DATABASE_PATH
from app.database import get_db
from app.cache import compute_error_signature, get_cached_triage, set_cached_triage
from app.llm_triage import analyze_incident_with_llm
from app.reporting import generate_incident_report

def process_incident_queue(batch_size: int = 10, db_path: str = DATABASE_PATH) -> Dict[str, Any]:
    """
    Asynchronous background job worker:
    - Fetches pending incidents off the HTTP request path
    - Uses TTL cache for repeated incident signatures
    - Executes LLM root-cause analysis on cache misses
    - Compiles executive post-mortem reports
    """
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, service_name, error_message, stack_trace, severity
            FROM incidents
            WHERE status = 'pending_triage'
            ORDER BY ingested_at ASC
            LIMIT ?
            """,
            (batch_size,)
        )
        pending_rows = [dict(r) for r in cursor.fetchall()]

        # Fetch known runbooks
        cursor.execute("SELECT id, service_name, title, error_pattern, remediation_steps FROM runbooks")
        runbooks = [dict(r) for r in cursor.fetchall()]

    stats = {
        "processed_count": len(pending_rows),
        "cache_hits": 0,
        "cache_misses": 0,
        "reports_generated": 0,
        "details": []
    }

    for inc in pending_rows:
        inc_id = inc["id"]
        sig = compute_error_signature(inc["service_name"], inc["error_message"], inc["stack_trace"])

        # 1. Check TTL cache
        cached = get_cached_triage(sig, db_path)
        if cached:
            stats["cache_hits"] += 1
            root_cause = cached["root_cause_hypothesis"]
            triage_summary = f"[CACHE HIT] Reused verified root-cause analysis for {inc['service_name']} (0ms compute)."
        else:
            stats["cache_misses"] += 1
            # Run narrow AI triage
            analysis = analyze_incident_with_llm(
                service_name=inc["service_name"],
                error_message=inc["error_message"],
                stack_trace=inc["stack_trace"],
                runbooks=[rb for rb in runbooks if rb["service_name"] == inc["service_name"] or rb["service_name"] == "*"],
                db_path=db_path
            )
            root_cause = analysis.root_cause_hypothesis
            triage_summary = (
                f"Triaged via IncidentPulse AI ({analysis.severity_assessment}). "
                f"Confidence: {analysis.confidence_score * 100:.0f}%. "
                f"Matched Runbook: {analysis.matched_runbook_id or 'None'}."
            )
            # Store into cache
            set_cached_triage(sig, root_cause, [s.model_dump() for s in analysis.mitigation_steps], db_path=db_path)

        # 2. Update incident record
        with get_db(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE incidents
                SET status = 'triaged',
                    root_cause = ?,
                    triage_summary = ?
                WHERE id = ?
                """,
                (root_cause, triage_summary, inc_id)
            )
            conn.commit()

        # 3. Generate Executive Report
        rep = generate_incident_report(inc_id, db_path)
        stats["reports_generated"] += 1

        stats["details"].append({
            "incident_id": inc_id,
            "service_name": inc["service_name"],
            "root_cause": root_cause,
            "cached": bool(cached),
            "report_id": rep["id"]
        })

    return stats

