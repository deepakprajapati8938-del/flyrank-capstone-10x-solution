import hashlib
import json
import datetime
from typing import Optional, Dict, Any
from app.config import DATABASE_PATH, CACHE_TTL_SECONDS
from app.database import get_db

# Fast in-memory cache layer for instant retrieval
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

def compute_error_signature(service_name: str, error_message: str, stack_trace: str) -> str:
    """Computes a deterministic fingerprint of an error for caching duplicate incidents."""
    # Normalize error message by removing transient numbers, timestamps, and memory hex addresses
    import re
    normalized_err = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", error_message)
    normalized_err = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "TIMESTAMP", normalized_err)
    key_str = f"{service_name.strip().lower()}|{normalized_err.strip().lower()}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

def get_cached_triage(signature_hash: str, db_path: str = DATABASE_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves cached incident triage if unexpired (checks in-memory then SQLite)."""
    now = datetime.datetime.utcnow()

    # 1. Check in-memory fast tier
    if signature_hash in _MEMORY_CACHE:
        entry = _MEMORY_CACHE[signature_hash]
        if entry["expires_at"] > now:
            return entry["data"]
        else:
            del _MEMORY_CACHE[signature_hash]

    # 2. Check SQLite persistent cache
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT root_cause, mitigation_steps, expires_at FROM triage_cache WHERE signature_hash = ?",
            (signature_hash,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        exp_iso = row["expires_at"]
        expires_at = datetime.datetime.fromisoformat(exp_iso)
        if expires_at < now:
            cursor.execute("DELETE FROM triage_cache WHERE signature_hash = ?", (signature_hash,))
            conn.commit()
            return None

        data = {
            "root_cause_hypothesis": row["root_cause"],
            "mitigation_steps": json.loads(row["mitigation_steps"]),
            "from_cache": True
        }
        # Populate in-memory tier
        _MEMORY_CACHE[signature_hash] = {"data": data, "expires_at": expires_at}
        return data

def set_cached_triage(
    signature_hash: str,
    root_cause: str,
    mitigation_steps: Any,
    ttl_seconds: int = CACHE_TTL_SECONDS,
    db_path: str = DATABASE_PATH
):
    """Caches triage result in memory and SQLite with TTL."""
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(seconds=ttl_seconds)

    steps_json = json.dumps(mitigation_steps) if not isinstance(mitigation_steps, str) else mitigation_steps
    steps_obj = json.loads(steps_json) if isinstance(steps_json, str) else mitigation_steps

    # Save to in-memory
    _MEMORY_CACHE[signature_hash] = {
        "data": {
            "root_cause_hypothesis": root_cause,
            "mitigation_steps": steps_obj,
            "from_cache": True
        },
        "expires_at": expires_at
    }

    # Save to SQLite
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO triage_cache (signature_hash, root_cause, mitigation_steps, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (signature_hash, root_cause, steps_json, expires_at.isoformat())
        )
        conn.commit()
