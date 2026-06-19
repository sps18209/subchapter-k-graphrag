"""
audit.py — tamper-evident audit trail. Hash-chained and append-only.

Every record carries `seq`, the previous record's `prev` hash, and its own
`hash = sha256(prev + canonical(record))`. Altering, reordering, or dropping any record
breaks the chain, which `verify_chain()` detects. Records always go to stdout; if
`SUBK_AUDIT_LOG` is set they are also appended to that file. Pure stdlib.

For a legal product the audit trail is not optional: who asked what, as of which date,
what was surfaced or computed, and who approved any model-proposed enrichment.

Production: keep the hash chain, but point the sink at an APPEND-ONLY / immutable store —
a WORM object-storage bucket, or append-only Postgres with row-level security. The chain
makes tampering *detectable* regardless of sink; the immutable sink makes it *hard*. Rows
can carry client-matter facts (Rule 1.6): encrypt at rest, restrict access, set retention.

CLI:  python audit.py verify <logfile>   # walk the chain, report the first break
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timezone

GENESIS = "0" * 64
_LOG_PATH = os.environ.get("SUBK_AUDIT_LOG")
_lock = threading.Lock()
_state = {"seq": 0, "prev": GENESIS}


def _canonical(rec: dict) -> str:
    # deterministic serialization (sorted keys, no whitespace) so the hash is reproducible
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), default=str)


def _record_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + _canonical(body)).encode("utf-8")).hexdigest()


def _emit(line: str) -> None:
    sys.stdout.write("AUDIT " + line + "\n")
    sys.stdout.flush()
    if _LOG_PATH:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def audit_log(*, request_id: str, principal: str, action: str,
              status: int | None = None, duration_ms: float | None = None,
              detail: dict | None = None) -> dict:
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
    with _lock:  # chain state is shared across request threads
        record["seq"] = _state["seq"]
        record["prev"] = _state["prev"]
        record["hash"] = _record_hash(_state["prev"], record)  # record has no "hash" yet
        _state["seq"] += 1
        _state["prev"] = record["hash"]
        _emit(json.dumps(record, default=str))
    return record


def verify_chain(records: list[dict]) -> tuple[bool, str]:
    """Recompute the chain over an ordered list of records; report the first break."""
    prev = GENESIS
    for i, rec in enumerate(records):
        body = {k: v for k, v in rec.items() if k != "hash"}
        if rec.get("prev") != prev:
            return False, f"record {i} (seq {rec.get('seq')}): broken link — prev mismatch"
        if rec.get("hash") != _record_hash(prev, body):
            return False, f"record {i} (seq {rec.get('seq')}): hash mismatch — record was altered"
        prev = rec["hash"]
    return True, f"chain intact ({len(records)} records)"


def _load(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("AUDIT "):  # tolerate stdout-captured lines
                line = line[6:]
            if line:
                out.append(json.loads(line))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Audit-trail tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="verify a hash-chained audit log")
    v.add_argument("logfile")
    args = ap.parse_args()
    ok, msg = verify_chain(_load(args.logfile))
    print(msg)
    sys.exit(0 if ok else 1)
