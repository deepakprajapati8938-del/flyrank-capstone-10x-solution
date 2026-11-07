import sqlite3
from contextlib import contextmanager
from app.config import DATABASE_PATH

def init_db(db_path: str = DATABASE_PATH):
    """Initializes SQLite tables, WAL mode, and performance indexes."""
    with sqlite3.connect(db_path, timeout=10.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        cursor = conn.cursor()

        # 1. Users Table (Authentication & RBAC)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'engineer',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Incidents Table (Alert Ingestion & Triage State)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                service_name TEXT NOT NULL,
                error_message TEXT NOT NULL,
                stack_trace TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'high',
                status TEXT NOT NULL DEFAULT 'pending_triage',
                triage_summary TEXT,
                root_cause TEXT,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """)

        # 3. Runbooks Catalog Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runbooks (
                id TEXT PRIMARY KEY,
                service_name TEXT NOT NULL,
                title TEXT NOT NULL,
                error_pattern TEXT NOT NULL,
                remediation_steps TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Triage Cache Table (TTL Caching)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS triage_cache (
                signature_hash TEXT PRIMARY KEY,
                root_cause TEXT NOT NULL,
                mitigation_steps TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. AI Cost Logs Table (Per-call Audit & Budget Guard)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_cost_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                operation TEXT NOT NULL,
                model TEXT NOT NULL,
                input_units INTEGER NOT NULL,
                output_units INTEGER NOT NULL,
                cost_usd REAL NOT NULL
            )
        """)

        # 6. Incident Reports Table (Executive Post-Mortem Deliverables)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_reports (
                id TEXT PRIMARY KEY,
                incident_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                executive_summary TEXT NOT NULL,
                root_cause TEXT NOT NULL,
                mttr_minutes INTEGER NOT NULL,
                mitigation_steps TEXT NOT NULL,
                html_content TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (incident_id) REFERENCES incidents(id)
            )
        """)

        # 7. Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triage_signature ON triage_cache(signature_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_incident ON incident_reports(incident_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_timestamp ON ai_cost_logs(timestamp)")

        conn.commit()

@contextmanager
def get_db(db_path: str = DATABASE_PATH):
    """Context manager for SQLite connection with timeout."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
