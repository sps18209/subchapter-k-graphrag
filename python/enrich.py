#!/usr/bin/env python3
"""
enrich.py — Layer 2 semantic enrichment, GATED (production swap #3).

The security model, by construction:
  PROPOSE  An enricher drafts a plain-language gloss for a node. The draft is returned /
           queued — it is NEVER written to the graph. So retrieval and the currency gate
           cannot surface it: citable output is only ever structural + attorney-approved
           content. The model never writes citable law.
  PROMOTE  An attorney reviews a draft and applies it. Only this step mutates the graph,
           and it is attributed to the attorney (enrichment_status -> 'enriched').
  REJECT   Discard the draft. No graph change.

Providers (SUBK_ENRICH_PROVIDER):
  unset / "none"  -> enrichment disabled (default).
  "stub"          -> StubEnricher: deterministic, offline, no key, no network. Lets the
                     whole propose -> gate -> promote loop run and be tested everywhere.
  "openai"        -> OpenAIEnricher: real drafts via the API (needs OPENAI_API_KEY). Sends
                     ONLY public corpus text (citation/label/existing synthesis) — never
                     /ask or /compute inputs, so no client-matter data leaves. Use a
                     zero-data-retention / no-train account. See DEPLOY.md (Rule 1.6).

CLI:
  python enrich.py propose <node_id>                 # draft a gloss (writes proposals/<id>.json)
  python enrich.py review                            # list pending proposals
  python enrich.py promote <node_id> --attorney NAME # apply a reviewed draft to subk.db
  python enrich.py reject  <node_id>                 # discard a draft
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

import graph

DRAFT_PREFIX = "[DRAFT—unverified, attorney review required] "
PROPOSALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proposals")


# -- providers ------------------------------------------------------------------
class StubEnricher:
    """Offline, deterministic draft generator — for running/testing the gated loop."""
    name = "stub"

    def propose_synthesis(self, node: dict) -> str:
        return (DRAFT_PREFIX + f"Plain-language gloss of {node['citation']} "
                f"({node['label']}). Source note: {node['synthesis'] or '(none)'}")


class OpenAIEnricher:
    """Real drafts via the OpenAI API. Sends only public corpus text, never user queries."""
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None):
        self.model = model or os.environ.get("SUBK_ENRICH_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set (required for SUBK_ENRICH_PROVIDER=openai)")

    def propose_synthesis(self, node: dict) -> str:
        sys_msg = ("You draft concise, plain-language glosses of U.S. partnership-tax "
                   "authorities for attorney review. Be precise, cite nothing new, and never "
                   "assert something is current law. 2-3 sentences.")
        user_msg = (f"Citation: {node['citation']}\nLabel: {node['label']}\n"
                    f"Existing note: {node['synthesis'] or '(none)'}\n\nDraft a plain-language gloss.")
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "system", "content": sys_msg},
                                        {"role": "user", "content": user_msg}]}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return DRAFT_PREFIX + data["choices"][0]["message"]["content"].strip()


def get_enricher(provider: str | None = None):
    provider = provider if provider is not None else os.environ.get("SUBK_ENRICH_PROVIDER")
    if not provider or provider == "none":
        return None
    if provider == "stub":
        return StubEnricher()
    if provider == "openai":
        return OpenAIEnricher()
    raise ValueError(f"unknown SUBK_ENRICH_PROVIDER: {provider!r} (use none|stub|openai)")


# -- the gated workflow ---------------------------------------------------------
def propose(con, node_id: str, enricher) -> dict:
    """Draft an enrichment. Returns a proposal; does NOT touch the graph (the gate)."""
    n = graph.node(con, node_id)
    if not n:
        raise ValueError(f"no node '{node_id}'")
    return {
        "node_id": node_id,
        "kind": "synthesis",
        "current": n["synthesis"],
        "draft": enricher.propose_synthesis(n),
        "model": enricher.name,
        "status": "proposed",
        "proposed_at": datetime.now(timezone.utc).isoformat(),
    }


def promote(con, proposal: dict, attorney: str) -> dict:
    """Apply a reviewed draft to the graph, attributed to the attorney. The ONLY writer."""
    if not attorney:
        raise ValueError("promotion requires an attorney identity (who approved it)")
    con.execute("UPDATE node SET synthesis=?, enrichment_status='enriched' WHERE id=?",
                (proposal["draft"], proposal["node_id"]))
    getattr(con, "commit", lambda: None)()  # sqlite needs commit; pg wrapper is autocommit
    return {"action": "promote", "node_id": proposal["node_id"], "attorney": attorney,
            "model": proposal.get("model"), "at": datetime.now(timezone.utc).isoformat()}


def reject(proposal: dict, reason: str = "") -> dict:
    """Discard a draft. No graph change."""
    return {"action": "reject", "node_id": proposal["node_id"], "reason": reason}


# -- CLI ------------------------------------------------------------------------
def _con():
    db = os.environ.get("SUBK_DB", "subk.db")
    if not os.path.exists(db):
        return graph.build(db)
    import sqlite3
    return sqlite3.connect(db)


def _path(node_id):
    return os.path.join(PROPOSALS_DIR, node_id + ".json")


def main():
    ap = argparse.ArgumentParser(description="Gated enrichment for the Subchapter K graph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose"); p.add_argument("node_id")
    sub.add_parser("review")
    pr = sub.add_parser("promote"); pr.add_argument("node_id"); pr.add_argument("--attorney", required=True)
    rj = sub.add_parser("reject"); rj.add_argument("node_id"); rj.add_argument("--reason", default="")
    args = ap.parse_args()
    con = _con()

    if args.cmd == "propose":
        enricher = get_enricher() or StubEnricher()
        prop = propose(con, args.node_id, enricher)
        os.makedirs(PROPOSALS_DIR, exist_ok=True)
        with open(_path(args.node_id), "w") as f:
            json.dump(prop, f, indent=2)
        print(json.dumps(prop, indent=2))
        print(f"\nqueued -> {_path(args.node_id)}  (review, then: enrich.py promote {args.node_id} --attorney YOU)")
    elif args.cmd == "review":
        if not os.path.isdir(PROPOSALS_DIR) or not os.listdir(PROPOSALS_DIR):
            print("no pending proposals"); return
        for fn in sorted(os.listdir(PROPOSALS_DIR)):
            prop = json.load(open(os.path.join(PROPOSALS_DIR, fn)))
            print(f"- {prop['node_id']} ({prop['model']}): {prop['draft'][:90]}...")
    elif args.cmd == "promote":
        prop = json.load(open(_path(args.node_id)))
        print(json.dumps(promote(con, prop, args.attorney)))
        os.remove(_path(args.node_id))
        print(f"promoted {args.node_id}; graph updated (enrichment_status=enriched).")
    elif args.cmd == "reject":
        prop = json.load(open(_path(args.node_id)))
        print(json.dumps(reject(prop, args.reason)))
        os.remove(_path(args.node_id))


if __name__ == "__main__":
    main()
