import sys
import json
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import DATABASE_PATH
from app.database import init_db, get_db
from app.auth import hash_password

def seed_database(db_path: str = DATABASE_PATH):
    print("=========================================================")
    print("[SEED] INCIDENTPULSE — AUTONOMOUS INCIDENT TRIAGE ENGINE")
    print(f"[SEED] Database Target: {db_path}")
    print("=========================================================")

    # 1. Initialize schema
    init_db(db_path)
    print("[OK] Initialized SQLite tables and performance indexes.")

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM incident_reports")
        cursor.execute("DELETE FROM triage_cache")
        cursor.execute("DELETE FROM ai_cost_logs")
        cursor.execute("DELETE FROM incidents")
        cursor.execute("DELETE FROM runbooks")
        cursor.execute("DELETE FROM users")

        # 2. Seed Default Users
        admin_pwd = hash_password("adminpassword123")
        eng_pwd = hash_password("engineerpassword123")

        cursor.execute(
            "INSERT INTO users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("usr_admin_001", "admin@company.com", admin_pwd, "admin")
        )
        cursor.execute(
            "INSERT INTO users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("usr_eng_002", "engineer@company.com", eng_pwd, "engineer")
        )

        # 3. Seed Production Runbooks
        runbooks = [
            (
                "rb_payment_01",
                "payment-service",
                "Payment Gateway DB Pool Saturation",
                "ConnectionPoolTimeoutException",
                json.dumps([
                    {"action": "Inspect active PostgreSQL backend connections", "command_or_fix": "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"},
                    {"action": "Scale PgBouncer client pool size to 250", "command_or_fix": "SET max_client_conn = 250;"},
                    {"action": "Cycle saturated transaction worker pods", "command_or_fix": "kubectl rollout restart deployment/payment-worker"}
                ])
            ),
            (
                "rb_auth_02",
                "auth-service",
                "Auth Token Signature Drift & Skew",
                "ExpiredSignatureError",
                json.dumps([
                    {"action": "Check system host time against cloud NTP server", "command_or_fix": "chronyc tracking"},
                    {"action": "Validate JWKS public key rotation cache", "command_or_fix": "curl -s https://auth.company.com/.well-known/jwks.json"},
                    {"action": "Gracefully extend token validation tolerance to 60s", "command_or_fix": "jwt.decode(..., leeway=60)"}
                ])
            ),
            (
                "rb_search_03",
                "search-service",
                "JVM Heap Memory Out of Memory Crash",
                "OutOfMemoryError: Java heap space",
                json.dumps([
                    {"action": "Collect automated heap dump before container terminates", "command_or_fix": "-XX:+HeapDumpOnOutOfMemoryError"},
                    {"action": "Bump pod memory limit from 2Gi to 4Gi", "command_or_fix": "kubectl set resources deployment search --limits=memory=4Gi"}
                ])
            )
        ]

        for rid, sname, title, pattern, steps in runbooks:
            cursor.execute(
                """
                INSERT INTO runbooks (id, service_name, title, error_pattern, remediation_steps)
                VALUES (?, ?, ?, ?, ?)
                """,
                (rid, sname, title, pattern, steps)
            )

        # 4. Seed Test Incidents (Queued for Autonomous Triage)
        incidents = [
            (
                "inc_demo_payment_01",
                "payment-service",
                "ConnectionPoolTimeoutException: Timeout waiting for idle object in pool after 5000ms",
                "org.postgresql.util.PSQLException: ConnectionPoolTimeoutException: Timeout waiting for idle object in pool at com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:186)",
                "critical",
                "pending_triage"
            ),
            (
                "inc_demo_auth_02",
                "auth-service",
                "ExpiredSignatureError: Signature has expired at timestamp 1714000000",
                "jwt.exceptions.ExpiredSignatureError: Signature has expired at /app/auth.py:48 in verify_token",
                "high",
                "pending_triage"
            )
        ]

        for iid, sname, emsg, strace, sev, st in incidents:
            cursor.execute(
                """
                INSERT INTO incidents (id, service_name, error_message, stack_trace, severity, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (iid, sname, emsg, strace, sev, st)
            )

        conn.commit()

    print("[OK] Seeded 2 Users: 'admin@company.com' (admin) and 'engineer@company.com' (engineer).")
    print("[OK] Seeded 3 Runbooks for payment-service, auth-service, and search-service.")
    print("[OK] Seeded 2 Ingested Incidents queued for background triage.")
    print("\n[COMPLETE] Seed complete! System is primed for acceptance probes.")
    print("=========================================================")

seed_demo_data = seed_database

if __name__ == "__main__":
    seed_database()
