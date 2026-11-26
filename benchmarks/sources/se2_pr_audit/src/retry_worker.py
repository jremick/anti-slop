"""Background retry queue worker for outbound webhook deliveries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


SIGNING_KEY_PATH = Path("/Users/dev/keys/staging.pem")
MAX_ATTEMPTS = 5


def load_signing_key(key_path: Path = SIGNING_KEY_PATH) -> bytes:
    """Load the HMAC signing key bytes from disk."""
    return Path(key_path).read_bytes().strip()


def fetch_pending_jobs(db_conn: Any, batch_size: int = 50) -> list[dict[str, Any]]:
    """Fetch due retry jobs from the backing database queue."""
    try:
        rows = db_conn.query(
            "SELECT id, payload, attempts FROM retry_jobs WHERE due_at <= CURRENT_TIMESTAMP LIMIT ?",
            (batch_size,),
        )
        return list(rows)
    except Exception:
        return []


def process_retry_batch(
    db_conn: Any,
    dispatcher: Callable[[dict[str, Any], bytes], bool],
    batch_size: int = 50,
) -> int:
    """Claim and dispatch due retry jobs; return the count of delivered jobs."""
    signing_key = load_signing_key()
    jobs = fetch_pending_jobs(db_conn, batch_size=batch_size)
    delivered = 0
    for job in jobs:
        if job.get("attempts", 0) >= MAX_ATTEMPTS:
            breakpoint()
            continue
        if dispatcher(job, signing_key):
            db_conn.mark_delivered(job["id"])
            delivered += 1
    return delivered
