#!/usr/bin/env python3
"""
subk_intake.py — the ingestion engine. Turns inputs into a verifiable SEE fact-frame and
reports, transparently, what it could and could NOT take in.

Two doors:
  • a matter FOLDER of documents (the real path) — agreement + capital-account statements, etc.
  • pasted/structured FACTS (the light path) — for hypotheticals and study.

Reliability guarantees:
  • READ-ONLY — never modifies or deletes your source files.
  • Degrades gracefully — uses only the extraction backends actually installed; an unreadable
    file is REPORTED (skipped + why), never guessed at.
  • Deterministic provision detection — agreement provisions (DRO, QIO, capital-account
    maintenance, liquidation-per-CA) are found by literal phrase match, and the matched sentence
    becomes the field's verbatim quote — so every detected fact is traceable to its source text.
"""
from __future__ import annotations

import os
import re

import subk_doctrine
import subk_see

# ---- where files come from -------------------------------------------------------------------
# Home dir (not ~/Downloads): macOS blocks Terminal writes to ~/Downloads. Drop documents here.
MATTERS_ROOT = os.path.expanduser("~/subk-matters")
TEXT_EXT = {".txt", ".md"}
RICH_EXT = {".pdf", ".docx"}
SUPPORTED_EXT = TEXT_EXT | RICH_EXT


def slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-") or "matter"


def matter_dir(name: str, create: bool = True) -> str:
    d = os.path.join(MATTERS_ROOT, slugify(name))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


# ---- extraction (read-only, only installed backends) -----------------------------------------
def _extract(path: str) -> tuple[str, str, str]:
    """Return (text, backend, status). status is 'ok' or 'skipped: <reason>' — never an exception."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in TEXT_EXT:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read(), "text", "ok"
        if ext == ".pdf":
            try:
                import pdfplumber
            except ImportError:
                return "", "-", "skipped: install pdfplumber to read PDFs"
            out = []
            with pdfplumber.open(path) as pdf:
                for pg in pdf.pages:
                    out.append(pg.extract_text() or "")
            text = "\n".join(out).strip()
            if len(text) < 40 * max(1, len(out)):
                return text, "pdfplumber", "ok: low text yield (likely scanned — OCR backend not wired)"
            return text, "pdfplumber", "ok"
        if ext == ".docx":
            try:
                import docx
            except ImportError:
                return "", "-", "skipped: install python-docx to read .docx"
            return "\n".join(p.text for p in docx.Document(path).paragraphs), "python-docx", "ok"
        return "", "-", f"skipped: unsupported type {ext or '(none)'}"
    except Exception as e:
        return "", "-", f"skipped: could not read ({type(e).__name__})"


def ingest_folder(path: str) -> dict:
    """Walk a folder READ-ONLY; return combined facts text + a per-file report. Never raises on a
    bad file — it lands in the report as skipped."""
    report, chunks = [], []
    if not os.path.isdir(path):
        return {"facts": "", "report": [], "error": f"no such folder: {path}"}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            fp = os.path.join(root, fn)
            text, backend, status = _extract(fp)
            report.append({"file": os.path.relpath(fp, path), "backend": backend,
                           "chars": len(text), "status": status})
            if text.strip():
                chunks.append(f"## {os.path.relpath(fp, path)}\n<!-- extractor: {backend} -->\n\n{text}\n")
    return {"facts": "\n".join(chunks), "report": report, "error": None}


# ---- scope: which doctrine, if any, fits this matter? ----------------------------------------
def scope_check(text: str, doctrine=None) -> dict:
    """If `doctrine` is given, check only that one; otherwise autodetect by signal score across all
    wired doctrines. Returns the picked doctrine + signal hits, or out-of-scope if nothing matched."""
    t = (text or "").lower()
    if doctrine is not None:
        hits = [s for s in doctrine.SCOPE_SIGNALS if s in t]
        return {"in_scope": bool(hits), "doctrine": doctrine.DOCTRINE, "signals": hits,
                "reason": (f"matches {doctrine.DOCTRINE} signals" if hits else
                           f"no {doctrine.DOCTRINE} signals found in the issue text")}
    pick, score, scores = subk_doctrine.autodetect(t)
    if pick is None:
        return {"in_scope": False, "doctrine": None, "signals": [], "scores": scores,
                "reason": "no doctrine signals matched (wired: " + ", ".join(subk_doctrine.names()) + ")"}
    return {"in_scope": True, "doctrine": pick.DOCTRINE,
            "signals": [s for s in pick.SCOPE_SIGNALS if s in t], "scores": scores,
            "reason": f"autodetected {pick.DOCTRINE} (score {score})"}


# ---- deterministic provision detection (phrase match -> verbatim quote) -----------------------
def _sentence_around(text: str, start: int, end: int) -> str:
    a = text.rfind(".", 0, start) + 1
    b = text.find(".", end)
    b = b + 1 if b != -1 else len(text)
    return re.sub(r"\s+", " ", text[a:b]).strip()[:300]


def detect_provisions(text: str, source: str = "facts", doctrine=None) -> dict:
    """Fill the doctrine's frame from literal phrase matches in `text`. Each detected field carries
    the actual sentence it was found in (string-verifiable). Fields the patterns can't detect stay
    null — the tool then reports them as missing rather than guess. Defaults to the SEE doctrine."""
    d = doctrine or subk_see
    frame = d.empty_frame()
    for field, pat in d.PROVISION_PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            frame["fields"][field] = {"value": True, "quote": _sentence_around(text, m.start(), m.end()),
                                      "source": source}
    if text.strip():
        frame["sources"].append(source)
    return frame


# ---- anonymized party intake -----------------------------------------------------------------
# Anonymize at the SOURCE: the attorney enters short codes (e.g. 'RoSm' = Robert Smith) and the
# real-name<->code map stays with the attorney (privileged). The tool only ever holds the codes,
# so no real name enters the system — for local OR cloud. Masking is then just a backstop.
def parse_parties(spec: str) -> list:
    """Parse 'RoSm:contributing, ToJo:service' -> [{code, role}]."""
    out = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        code, _, role = chunk.partition(":")
        out.append({"code": code.strip(), "role": role.strip()})
    return out


def looks_identifying(code: str) -> bool:
    """Best-effort nudge: a code with a space or that's long probably IS a real name, not a code."""
    return (" " in code.strip()) or len(code.strip()) > 12


def roster_text(parties: list) -> str:
    return "; ".join(p["code"] + (f" ({p['role']})" if p.get("role") else "") for p in parties)


_PARTNER_ROLES = {"contributing", "service", "managing", "limited", "general", "capital"}


def role_label(role: str, used: set) -> str:
    """Turn a role into the party's canonical, FUNCTIONAL label — what it truly is in the deal, not
    a name or a name-derived code. 'contributing' -> 'Contributing partner'; 'employee' -> 'Employee';
    blank -> 'Party'. Disambiguated with a number if the same role recurs (Plaintiff, Plaintiff 2)."""
    base = (role or "").strip().lower() or "party"
    if base in _PARTNER_ROLES and "partner" not in base:
        base += " partner"
    base = base[:1].upper() + base[1:]
    label, n = base, 2
    while label in used:
        label, n = f"{base} {n}", n + 1
    used.add(label)
    return label


def frame_from_form(form: dict, doctrine=None) -> dict:
    """Light path: attorney-supplied dict of field -> value. Quote = the supplied value, source =
    'attorney input'. Unknown keys are ignored; only the closed vocabulary of the picked doctrine
    is accepted. Defaults to the SEE doctrine for backward compatibility."""
    d = doctrine or subk_see
    frame = d.empty_frame()
    for field in d.FRAME_FIELDS:
        if field in form and form[field] not in (None, ""):
            frame["fields"][field] = {"value": form[field], "quote": str(form[field]),
                                      "source": "attorney input"}
    frame["sources"].append("attorney input")
    return frame
