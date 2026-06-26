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

import datetime
import hashlib
import json
import os
import re

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

def system_prompt(doctrine) -> str:
    """The model is given a doctrine-aware system prompt — built from the doctrine module's own
    DESCRIPTION, EXAMPLE_TAG, and ULTIMATE_CONCLUSION_PHRASE — so the two halves of the sandwich
    can never disagree on what's being analyzed. The closure rule and the augmentation contract
    are universal."""
    return (
        f"You analyze {doctrine.DESCRIPTION}. You are sandwiched between two deterministic "
        "verification layers and must obey the closure rule:\n"
        "THE LEGAL CONTENT OF YOUR OUTPUT MUST TRACE ENTIRELY TO THE PROVIDED BUNDLE.\n"
        "- The bundle lists VERIFIED items, each with a stable ID (LAW:…, CITE:…, FACT:…). These "
        "are the ONLY legal facts you may rely on.\n"
        "- Map the facts to the factors of the test. Every LEGAL proposition must (a) carry an "
        f"inline tag like {doctrine.EXAMPLE_TAG} in its text AND (b) list those same IDs in "
        "`supports`. Never assert a law, cite, or legal fact that isn't a bundle ID.\n"
        f"- Do NOT state the ultimate legal conclusion ({doctrine.ULTIMATE_CONCLUSION_PHRASE}) — "
        "that is the attorney's call. Put the precise question in `ultimate_question`.\n"
        "- You MAY add non-legal context ONLY in `augmentations`, each in one closed category "
        "(HISTORICAL/STATISTIC/ECONOMIC/FINANCIAL/BUSINESS), each with a `source`. An augmentation "
        "may never state a legal status or consequence.\n"
        "- List anything you lacked in `gaps`."
    )


# ---- Layer A: assemble the verified bundle ----------------------------------------------------
def build_bundle(frame: dict, authority: dict, holdings: list | None = None, doctrine=None) -> dict:
    """Return {items:[{id,kind,text}], ids:set, text:str, doctrine:str}. Only verified/known material
    enters. Doctrine defaults to SEE for backward compatibility."""
    d = doctrine or subk_see
    items = []
    # LAW: one item per leaf factor, tagged with its reg subsection.
    for fac in d.FACTORS:
        if "needs" not in fac:
            continue
        items.append({"id": f"LAW:{fac['id']}", "kind": "law",
                      "text": f"{fac['label']} — {fac['reg']}"})
    items.append({"id": "LAW:ROOT", "kind": "law",
                  "text": f"{d.ROOT_CITE} — verified {authority.get('status', '?')}"
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
    return {"items": items, "ids": ids, "text": text, "doctrine": d.DOCTRINE}


def bundle_key(bundle: dict) -> str:
    h = hashlib.sha256(bundle["text"].encode("utf-8")).hexdigest()[:16]
    doc = bundle.get("doctrine", "see")
    return f"{h}.{doc}.{PINNED_MODEL}.{PROMPT_VERSION}.{SCHEMA_VERSION}"


# ---- model providers ----------------------------------------------------------------------
# 'anthropic' (cloud, pinned, masked, ZDR-gated) | 'ollama' (fully local, nothing leaves the box)
def provider() -> str:
    return os.environ.get("SUBK_LLM_PROVIDER", "anthropic")


def _cache_path(key: str) -> str:
    d = os.path.expanduser("~/subk-matters/.llm-cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key + ".json")


def _masked_user(bundle: dict, question: str, redactor=None):
    """Build the user payload. FACT/CITE item text is first REDACTED (real names -> codes, always,
    if a redactor is given) then MASKED (amounts/EIN -> tokens). LAW items are left intact (the model
    needs the real reg). Deterministic, so the masker reconstructs identically on a cache hit. Masking
    defaults ON for the cloud provider, OFF for local; SUBK_LLM_MASK overrides. Returns (user, masker)."""
    masker = mask.Masker()
    default = "1" if provider() == "anthropic" else "0"
    do_mask = os.environ.get("SUBK_LLM_MASK", default) != "0"

    def prep(text: str, is_law: bool) -> str:
        if is_law:
            return text
        if redactor is not None:
            text = redactor.redact(text)        # names -> codes (always, before anything leaves)
        return masker.mask(text) if do_mask else text

    body = "\n".join(f"[{it['id']}] {prep(it['text'], it['kind'] == 'law')}" for it in bundle["items"])
    q = prep(question, False)
    user = f"QUESTION: {q}\n\nVERIFIED BUNDLE (the only legal facts you may use):\n{body}"
    return user, masker


def _emit_anthropic(user: str, sysprompt: str) -> dict | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=os.environ.get("SUBK_LLM_MODEL", PINNED_MODEL), max_tokens=8000, system=sysprompt,
        tools=[{"name": "emit_analysis", "description": "Emit the structured doctrine analysis.",
                "input_schema": ENVELOPE_SCHEMA, "strict": True}],
        tool_choice={"type": "tool", "name": "emit_analysis"},
        messages=[{"role": "user", "content": user}],
    )
    return next((b.input for b in resp.content
                 if getattr(b, "type", None) == "tool_use" and b.name == "emit_analysis"), None)


def _emit_ollama(user: str, sysprompt: str) -> dict | None:
    """Fully local: Ollama with JSON-schema structured output. Nothing leaves the machine. A weak
    local model can only produce a weak or malformed envelope — Layer B rejects anything ungrounded,
    so it can never present invented law as verified."""
    import urllib.request
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
    model = os.environ.get("SUBK_LLM_OLLAMA_MODEL", "llama3.2:3b")
    payload = {"model": model, "stream": False, "options": {"temperature": 0}, "format": ENVELOPE_SCHEMA,
               "messages": [{"role": "system", "content": sysprompt}, {"role": "user", "content": user}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            content = json.loads(r.read())["message"]["content"]
        env = json.loads(content)
        return env if isinstance(env, dict) and "propositions" in env else None
    except Exception:
        return None


class EgressBlocked(Exception):
    """Raised at the single exit when a registered client identifier would leave the machine."""


def assert_clean(payload: str, redactor) -> None:
    """FAIL-CLOSED invariant at the one egress point: every name the redactor was told to scrub MUST
    be gone from the payload. If one survived (a redaction bug / future code drift), refuse to send
    rather than scrub-and-hope. The error never contains the name (it would leak into logs)."""
    if redactor is None:
        return
    for name in redactor.names:
        if re.search(r"\b" + re.escape(name) + r"\b", payload, re.I):
            raise EgressBlocked("a registered client identifier survived redaction — send refused")


def _egress_log(provider_name: str, model: str, key: str, payload: str, redactor, masker) -> None:
    """Append a local, tamper-evident record of what left: a sha256 of the SCRUBBED payload + a
    redaction summary (role labels are safe to log; real names are NEVER logged). Best-effort."""
    try:
        log = os.environ.get("SUBK_EGRESS_LOG", os.path.expanduser("~/subk-matters/.egress-log.jsonl"))
        os.makedirs(os.path.dirname(log), exist_ok=True)
        prev = "genesis"
        if os.path.exists(log):
            with open(log, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if lines:
                prev = json.loads(lines[-1]).get("chain", "genesis")
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "provider": provider_name, "model": model, "bundle_key": key,
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "payload_chars": len(payload),
            "name_substitutions": len(redactor.codes) if redactor else 0,
            "roles": redactor.codes if redactor else [],     # functional roles only — not names
            "masks": len(masker.map) if masker else 0,
        }
        rec["chain"] = hashlib.sha256((prev + json.dumps(rec, sort_keys=True)).encode()).hexdigest()[:16]
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass   # logging must never block or crash a send


def analyze(bundle: dict, question: str, use_cache: bool = True, redactor=None):
    """Run the middle of the sandwich over the REDACTED + masked bundle. Returns (envelope, masker):
    envelope is the model's structured output or None (no key/SDK/local server → caller stays at the
    boundary). The SINGLE egress point: assert_clean() fails closed if a registered name survived, and
    every actual send is recorded to the local egress log. Cache hits don't send (no egress)."""
    prov = provider()
    key = bundle_key(bundle)
    path = _cache_path(f"{key}.{prov}")
    user, masker = _masked_user(bundle, question, redactor)   # rebuilt the same way on hit and miss
    if use_cache and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), masker                      # cache hit — nothing leaves the machine
    assert_clean(user, redactor)                              # <- fail-closed invariant, before any send
    model = (os.environ.get("SUBK_LLM_OLLAMA_MODEL", "llama3.2:3b") if prov == "ollama"
             else os.environ.get("SUBK_LLM_MODEL", PINNED_MODEL))
    _egress_log(prov, model, key, user, redactor, masker)     # <- provable record of exactly what left
    # Build a doctrine-aware system prompt so the model is told exactly the doctrine the bundle is for.
    import subk_doctrine
    d = subk_doctrine.resolve(bundle.get("doctrine", "")) or subk_see
    sp = system_prompt(d)
    envelope = _emit_ollama(user, sp) if prov == "ollama" else _emit_anthropic(user, sp)
    if envelope is not None and use_cache:
        with open(path, "w", encoding="utf-8") as fh:
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
