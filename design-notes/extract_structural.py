#!/usr/bin/env python3
"""
extract_structural.py — Layer 1 of the Tax Authority GraphRAG.

Deterministic, no-LLM structural extraction for one tax document. Given a source
document (its own citation + node_type + raw text), it emits one node for the
document plus one outbound edge per authority reference found in the text, each
classified by target type. This is the cheap, exhaustive layer: regex/parse only,
zero model calls. The whole point is that tax authority is already structured, so
the graph skeleton costs nothing to build.

Assumptions (surfaced up front, karpathy-style):
  - Input is plain text (IRB rulings, case text), OR you pre-flatten USLM / eCFR
    XML to one text blob per leaf provision before calling this. The XML structural
    parse is a separate feeder, not this file's job.
  - "Reference found in text" != "verified authority". Existence / good-law checks
    are Layer 0 (currency verifier), run AFTER this. This layer only finds edges.
  - authority_tier and validity intervals are assigned at ingest from the source,
    not inferred here.
  - Scope is federal; jurisdiction is fixed to 'US'.

Output: a dict {"nodes": [...], "edges": [...]}, JSON-serializable, matching
schema.sql. created_by is always 'deterministic' for everything this file emits.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict, field

JURISDICTION = "US"

# Authority tiers. Lower = stronger. Assigned at ingest, repeated here only so the
# emitted target stubs carry a sane default until the real node is ingested.
TIER = {
    "provision": 1,        # Internal Revenue Code (statute)
    "regulation": 3,       # Treasury Regulation (interpretive default; legislative = 2 at ingest)
    "ruling": 4,           # Rev. Rul. / Rev. Proc.
    "case": 4,             # judicial; reranked at ingest by court level
    "defined_term": 1,
}

# --- reference patterns -------------------------------------------------------
# Each returns (canonical_citation, target_node_type). Order matters: regs before
# bare sections so "§ 1.1031(a)-1" is not mis-read as IRC section 1.
PATTERNS = [
    # Treasury Regulation: Treas. Reg. § 1.1031(a)-1 ; Reg. 1.1031(k)-1 ; 26 CFR 1.61-1
    (re.compile(
        r"(?:Treas\.?\s*Reg\.?|Reg\.?|26\s*C\.?\s*F\.?\s*R\.?)\s*§?\s*"
        r"(1\.\d+[A-Za-z0-9().\-]*)", re.I), "regulation",
     lambda m: f"26 C.F.R. § {m.group(1).rstrip('.,;')}"),
    # Revenue Ruling: Rev. Rul. 2002-83
    (re.compile(r"Rev\.?\s*Rul\.?\s*(\d{2,4}[-\u2013]\d+)", re.I), "ruling",
     lambda m: f"Rev. Rul. {m.group(1).replace(chr(0x2013), '-')}"),
    # Revenue Procedure: Rev. Proc. 2008-16
    (re.compile(r"Rev\.?\s*Proc\.?\s*(\d{2,4}[-\u2013]\d+)", re.I), "ruling",
     lambda m: f"Rev. Proc. {m.group(1).replace(chr(0x2013), '-')}"),
    # IRC section with optional subsection path: section 1031(a)(2)(D) ; § 7701(o)
    (re.compile(
        r"(?:section|sec\.?|§)\s*(\d{1,4}[A-Z]?)((?:\([A-Za-z0-9]+\))*)", re.I),
     "provision",
     lambda m: f"26 U.S.C. § {m.group(1)}{m.group(2)}"),
]


def _edge_type(src_type: str, dst_type: str) -> str:
    """Classify an outbound reference by what links to what."""
    if dst_type == "ruling":
        return "cites"
    if dst_type == "case":
        return "cites"
    if src_type == "provision" and dst_type == "provision":
        return "cross_references"
    if src_type == "regulation" and dst_type == "provision":
        return "implements"
    if src_type == "ruling" and dst_type in ("provision", "regulation"):
        return "applies"
    if src_type == "case":
        return "interprets"
    return "cross_references"


def _slug(citation: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", citation.lower()).strip("-")


@dataclass
class Node:
    id: str
    node_type: str
    citation: str
    authority_tier: int
    jurisdiction: str = JURISDICTION
    enrichment_status: str = "structural"   # structural | enriched
    body: str = ""
    source_uri: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    created_by: str = "deterministic"


@dataclass
class Edge:
    id: str
    src_id: str
    dst_id: str
    edge_type: str
    created_by: str = "deterministic"
    confidence: float = 1.0   # deterministic structural edges are certain
    source_uri: str = ""


@dataclass
class Extraction:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


def extract(citation: str, node_type: str, text: str,
            source_uri: str = "", valid_from: str | None = None,
            valid_to: str | None = None) -> Extraction:
    """
    Extract the document node and all outbound structural edges from one document.

    Targets are emitted as lightweight stub nodes (enrichment_status='structural',
    no body) so the edge has somewhere to land. On real ingest the stub is upserted
    against the canonical node and the body/tier/validity are corrected from source.
    """
    src_id = _slug(citation)
    out = Extraction()
    out.nodes.append(Node(
        id=src_id, node_type=node_type, citation=citation,
        authority_tier=TIER.get(node_type, 5), body=text.strip(),
        source_uri=source_uri, valid_from=valid_from, valid_to=valid_to,
    ))

    seen_targets: set[str] = set()
    seen_edges: set[str] = set()
    # Work on a mutable copy: once a span is claimed by a higher-priority pattern
    # (regs before bare sections), blank it out so a later pattern cannot re-match
    # inside it. This is what kills the "1.1031(a)-1" -> spurious "section 1" bug.
    masked = list(text)
    for pattern, dst_type, canon in PATTERNS:
        current = "".join(masked)
        for m in pattern.finditer(current):
            dst_citation = canon(m)
            dst_id = _slug(dst_citation)
            for i in range(m.start(), m.end()):   # claim the span
                masked[i] = " "
            if dst_id == src_id:        # don't self-reference
                continue
            if dst_id not in seen_targets:
                seen_targets.add(dst_id)
                out.nodes.append(Node(
                    id=dst_id, node_type=dst_type, citation=dst_citation,
                    authority_tier=TIER.get(dst_type, 5),
                ))
            etype = _edge_type(node_type, dst_type)
            edge_id = f"{src_id}--{etype}--{dst_id}"
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                out.edges.append(Edge(
                    id=edge_id, src_id=src_id, dst_id=dst_id,
                    edge_type=etype, source_uri=source_uri,
                ))
    return out


def to_json(ex: Extraction) -> str:
    return json.dumps(
        {"nodes": [asdict(n) for n in ex.nodes],
         "edges": [asdict(e) for e in ex.edges]},
        indent=2)


# --- offline demo fixture: a trimmed but real-shaped §1031 + a ruling ----------
FIXTURE = {
    "citation": "26 U.S.C. § 1031(a)",
    "node_type": "provision",
    "valid_from": "2018-01-01",   # TCJA real-property limitation took effect
    "source_uri": "https://uscode.house.gov/...title26/section1031",
    "text": (
        "No gain or loss shall be recognized on the exchange of real property "
        "held for productive use in a trade or business or for investment if such "
        "real property is exchanged solely for real property of like kind. This "
        "subsection shall not apply to any exchange of property described in "
        "section 1031(a)(2). For the treatment of related-party exchanges see "
        "subsection (f), and for boot see section 1031(b). The basis rules of "
        "section 1031(d) apply. See also Treas. Reg. § 1.1031(a)-1 and "
        "Reg. 1.1031(k)-1. Cf. Rev. Rul. 2002-83 and Rev. Proc. 2008-16. The "
        "economic substance doctrine of section 7701(o) is unaffected."
    ),
}


if __name__ == "__main__":
    ex = extract(**FIXTURE)
    print(to_json(ex))
    n_real = sum(1 for n in ex.nodes if n.enrichment_status == "structural" and n.body)
    print(f"\n# {len(ex.nodes)} nodes ({n_real} sourced, "
          f"{len(ex.nodes) - n_real} stub targets), {len(ex.edges)} edges, "
          f"0 model calls", flush=True)
