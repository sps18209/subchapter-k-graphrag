"""
audit.py — audit-trail HOOK. Emits one structured JSON line per request to stdout.

For a legal product the audit trail is not optional: who asked what, as of which date,
what authority was surfaced, what was computed, and (in the enrichment build-out) who
approved any model-proposed node. This module is the seam where that record is written.

Production replacement: write to an APPEND-ONLY / immutable store — a hash-chained log,
a WORM object-storage bucket, or an append-only Postgres table with row-level security —
and treat the records as confidential. An audit row for an /ask or /compute call can
contain client matter facts, so it falls under the same confidentiality and retention
duties as the matter itself (Rule 1.6). Logging to stdout here keeps the shape visible;
it is not a compliant store.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def audit_log(*, request_id: str, principal: str, action: str,
              status: int | None = None, duration_ms: float | None = None,
              detail: dict | None = None) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "principal": principal,
        "action": action,
    }
    if status is not None:
        record["status"] = status
    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 1)
    if detail:
        record["detail"] = detail
    sys.stdout.write("AUDIT " + json.dumps(record, default=str) + "\n")
    sys.stdout.flush()
