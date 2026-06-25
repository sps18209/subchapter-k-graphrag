#!/usr/bin/env python3
"""
subk_llm.py — the reasoning sandwich: Layer A → Anthropic → Layer B.

  Layer A (deterministic)  assembles a VERIFIED context bundle — the SEE factor tree (each
                           factor's reg verified live against eCFR), matched holdings, and the
                           fact-frame — and stamps every item with a stable ID (LAW:… / CITE:… /
                           FACT:…). Only verified material crosses in.
  Anthropic (constrained)  reasons over the bundle into a RESTRICTED schema: every LEGAL
                           proposition must cite bundle IDs; non-legal context is segregated into
                           closed, cited, flagged augmentation categories. Pinned model, forced
                           tool-use, gated on ANTHROPIC_API_KEY. Determinism: forced schema +
                           a cache keyed on sha256(bundle)+versions (no temperature knob on Opus 4.8).
  Layer B (deterministic)  CLOSURE check: the legal content of the output ⊆ the verified input.
                           Every LEGAL proposition's supports must exist in the bundle and match
                           its inline tags; augmentations must be non-legal (lawfact gate) + sourced;
                           the ultimate conclusion is always returned flagged NEEDS_HUMAN.

If there is no API key (or the SDK isn't installed) analyze() returns None and the caller stays
at the local boundary — nothing leaves the machine. Layer A and Layer B are fully offline.
"""
from __future__ import annotations

import hashlib
import json
import os

import lawfact
import mask
import subk_see

PINNED_MODEL = "claude-opus-4-8"   # pin a specific model so results don't drift; bump deliberately
PROMPT_VERSION = "see-v1"
SCHEMA_VERSION = "envelope-v1"

AUG_CATEGORIES = ("HISTORICAL", "STATISTIC", "ECONOMIC", "FINANCIAL", "BUSINESS")

# The restricted output envelope the model is FORCED to emit (tool-use schema).
ENVELOPE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "propositions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
                "type": {"type": "string", "enum": ["LEGAL", "AUGMENTATION"]},
                "supports": {"type": "array", "items": {"type": "string"}},
            }, "required": ["text", "type", "supports"]}},
        "augmentations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
                "category": {"type": "string", "enum": list(AUG_CATEGORIES)},
                "source": {"type": "string"},
            }, "required": ["text", "category", "source"]}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "ultimate_question": {"type": "string"},
    }, "required": ["propositions", "augmentations", "gaps", "ultimate_question"],
}

SYSTEM_PROMPT = (
    "You analyze a substantial-economic-effect question (IRC 704(b)). You are sandwiched between "
    "two deterministic verification layers and must obey the closure rule:\n"
    "THE LEGAL CONTENT OF YOUR OUTPUT MUST TRACE ENTIRELY TO THE PROVIDED BUNDLE.\n"
    "- The bundle lists VERIFIED items, each with a stable ID (LAW:…, CITE:…, FACT:…). These are "
    "the ONLY legal facts you may rely on.\n"
    "- Map the facts to the factors of the test. Every LEGAL proposition must (a) carry an inline "
    "tag like [LAW:1.704-1(b)(2)(ii)(b)] in its text AND (b) list those same IDs in `supports`. "
    "Never assert a law, cite, or legal fact that isn't a bundle ID.\n"
    "- Do NOT state the ultimate legal conclusion (whether the allocation HAS substantial economic "
    "effect) — that is the attorney's call. Put the precise question in `ultimate_question`.\n"
    "- You MAY add non-legal context ONLY in `augmentations`, each in one closed category "
    "(HISTORICAL/STATISTIC/ECONOMIC/FINANCIAL/BUSINESS), each with a `source`. An augmentation may "
    "never state a legal status or consequence.\n"
    "- List anything you lacked in `gaps`."
)


# ---- Layer A: assemble the verified bundle ----------------------------------------------------
def build_bundle(frame: dict, authority: dict, holdings: list | None = None) -> dict:
    """Return {items:[{id,kind,text}], ids:set, text:str}. Only verified/known material enters."""
    items = []
    # LAW: one item per evaluable factor, tagged with its reg subsection.
    can, _ = subk_see.evaluable(frame)
    for fac in subk_see.FACTORS:
        if "needs" not in fac:
            continue
        items.append({"id": f"LAW:{fac['id']}", "kind": "law",
                      "text": f"{fac['label']} — {fac['reg']}"})
    items.append({"id": "LAW:ROOT", "kind": "law",
                  "text": f"{subk_see.ROOT_CITE} — verified {authority.get('status', '?')}"
                          + (f", current as of {authority['as_of']}" if authority.get("as_of") else "")})
    # CITE: matched holdings (already verified via CL/DAWSON).
    for h in holdings or []:
        items.append({"id": f"CITE:{h.get('id', 'case')}", "kind": "cite", "text": h.get("text", "")})
    # FACT: each filled fact-frame field, carrying its verbatim source quote.
    for field, v in frame["fields"].items():
        if v.get("value") is not None:
            q = v.get("quote") or str(v["value"])
            items.append({"id": f"FACT:{field}", "kind": "fact",
                          "text": f"{field} = {v['value']} (source: {v.get('source')}; \"{q[:160]}\")"})
    ids = {it["id"] for it in items}
    text = "\n".join(f"[{it['id']}] {it['text']}" for it in items)
    return {"items": items, "ids": ids, "text": text}


def bundle_key(bundle: dict) -> str:
    h = hashlib.sha256(bundle["text"].encode("utf-8")).hexdigest()[:16]
    return f"{h}.{PINNED_MODEL}.{PROMPT_VERSION}.{SCHEMA_VERSION}"


# ---- Anthropic: constrained, pinned, gated ----------------------------------------------------
def _cache_path(key: str) -> str:
    d = os.path.expanduser("~/subk-matters/.llm-cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key + ".json")


def _masked_user(bundle: dict, question: str):
    """Build the user payload with FACT/CITE item text MASKED (LAW items left intact — the model
    must see the real reg). Deterministic, so the masker reconstructs identically on a cache hit.
    Returns (user_text, masker). Masking is on unless SUBK_LLM_MASK=0."""
    masker = mask.Masker()
    if os.environ.get("SUBK_LLM_MASK", "1") == "0":
        body, q = bundle["text"], question
    else:
        body = "\n".join(f"[{it['id']}] " + (it["text"] if it["kind"] == "law" else masker.mask(it["text"]))
                         for it in bundle["items"])
        q = masker.mask(question)
    user = f"QUESTION: {q}\n\nVERIFIED BUNDLE (the only legal facts you may use):\n{body}"
    return user, masker


def analyze(bundle: dict, question: str, use_cache: bool = True):
    """Call the pinned model with forced-schema tool use over the MASKED bundle. Returns
    (envelope, masker): envelope is the validated dict (masked tokens intact) or None when no API
    key / SDK (caller then stays at the local boundary); masker un-masks for local display. The
    cache key is the UNMASKED bundle hash, so it's unique per matter; masking is reconstructed
    deterministically on a hit. Raw client identity never reaches the model or the cache file."""
    path = _cache_path(bundle_key(bundle))
    user, masker = _masked_user(bundle, question)   # rebuilt the same way on hit and miss
    if use_cache and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), masker
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, masker
    try:
        import anthropic
    except ImportError:
        return None, masker
    client = anthropic.Anthropic()
    model = os.environ.get("SUBK_LLM_MODEL", PINNED_MODEL)
    resp = client.messages.create(
        model=model, max_tokens=8000, system=SYSTEM_PROMPT,
        tools=[{"name": "emit_analysis", "description": "Emit the structured SEE analysis.",
                "input_schema": ENVELOPE_SCHEMA, "strict": True}],
        tool_choice={"type": "tool", "name": "emit_analysis"},
        messages=[{"role": "user", "content": user}],
    )
    envelope = next((b.input for b in resp.content
                     if getattr(b, "type", None) == "tool_use" and b.name == "emit_analysis"), None)
    if envelope is not None and use_cache:
        with open(path, "w", encoding="utf-8") as fh:    # stores masked tokens, never raw identity
            json.dump(envelope, fh, indent=2)
    return envelope, masker


# ---- Layer B: closure / match-back (deterministic) --------------------------------------------
import re

_TAG = re.compile(r"\[([A-Z]+:[^\]]+)\]")


def layer_b_verify(envelope: dict, bundle_ids: set) -> dict:
    """Prove the legal content of `envelope` traces entirely to `bundle_ids`. Returns a verdict
    with per-item problems. Nothing here calls a model — it's a string/ID + lawfact check."""
    props = []
    for p in envelope.get("propositions", []):
        text, ptype = p.get("text", ""), p.get("type")
        supports = p.get("supports", []) or []
        inline = set(_TAG.findall(text))
        problems = []
        if ptype == "LEGAL":
            if not supports:
                problems.append("LEGAL proposition with no bundle support → NEEDS_HUMAN")
            for s in supports:
                if s not in bundle_ids:
                    problems.append(f"support {s} is not in the verified bundle (invented)")
            for tag in inline:
                if tag not in supports:
                    problems.append(f"inline tag {tag} missing from supports[] (prose/array mismatch)")
        elif ptype == "AUGMENTATION":
            if lawfact.is_conclusion_of_law(text):
                problems.append("AUGMENTATION reads as a conclusion of law — only allowed as a "
                                "bundle-cited LEGAL proposition")
        props.append({**p, "verdict": "ok" if not problems else "rejected", "problems": problems})

    augs = []
    for a in envelope.get("augmentations", []):
        problems = []
        if a.get("category") not in AUG_CATEGORIES:
            problems.append("category not in the closed set")
        if not (a.get("source") or "").strip():
            problems.append("augmentation missing a source (must be cited + flagged)")
        if lawfact.is_conclusion_of_law(a.get("text", "")):
            problems.append("augmentation states a legal status/consequence — rejected")
        augs.append({**a, "verdict": "ok" if not problems else "rejected",
                     "problems": problems, "review_required": True})

    legal_ok = all(p["verdict"] == "ok" for p in props if p.get("type") == "LEGAL")
    aug_ok = all(a["verdict"] == "ok" for a in augs)
    return {
        "closed": legal_ok and aug_ok,
        "propositions": props,
        "augmentations": augs,
        "gaps": envelope.get("gaps", []),
        "ultimate_question": envelope.get("ultimate_question", ""),
        "conclusion": "NEEDS_HUMAN — the ultimate conclusion of law is the attorney's to make",
    }
