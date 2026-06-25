#!/usr/bin/env python3
"""
mask.py — local, reversible masking of client identifiers. Defense-in-depth for the reasoning
sandwich: identifiers in the FACT items are replaced with stable tokens before anything is sent
to the model, the model reasons over the tokens, and the tokens are restored LOCALLY for display.
The token->original map never leaves the machine.

Masked, high-precision: SSN, EIN, email, phone, dollar amounts, and entity names anchored on a
legal suffix (LLC / LP / Inc / Trust / Partners / …). NOT masked: bare personal names (need NER —
plug in Microsoft Presidio or spaCy via add_detector if you need them) and public LAW text (the
model must see the real reg). Deterministic: the same input yields the same tokens, so masking
reconstructs identically on a cache hit.

    m = mask.Masker()
    sent = m.mask("Acme Holdings LLC contributed $245,000")  # 'Acme Holdings LLC' -> [ENTITY_1] ...
    m.unmask(model_output)                                    # restores the originals for display
"""
from __future__ import annotations

import re

# (label, pattern) — order matters: most specific first so an EIN isn't half-eaten by AMOUNT.
_PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EIN", re.compile(r"\b\d{2}-\d{7}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ENTITY", re.compile(
        r"\b[A-Z][\w&.,'-]*(?:\s+[A-Z][\w&.,'-]*)*\s+"
        r"(?:LLC|L\.L\.C\.|LLP|LP|L\.P\.|Inc\.?|Corp\.?|Co\.|Company|Trust|Partners|Partnership|"
        r"Holdings|Associates|Group|Ventures|Capital)\b")),
    ("AMOUNT", re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:k|m|bn|million|billion|thousand)\b", re.I)),
]


class Masker:
    """Holds the per-run token map. Deterministic: a given original always maps to the same token
    within one Masker, and equal inputs across runs produce equal token assignments."""

    def __init__(self):
        self._fwd = {}                 # original -> token
        self._rev = {}                 # token -> original
        self._counts = {}              # label -> running count
        self._extra = []               # optional pluggable detectors (label, compiled-pattern)

    def add_detector(self, label: str, pattern) -> None:
        """Register an extra detector (e.g. a Presidio/spaCy-backed name pattern)."""
        self._extra.append((label, re.compile(pattern) if isinstance(pattern, str) else pattern))

    def _token(self, label: str, original: str) -> str:
        if original in self._fwd:
            return self._fwd[original]
        self._counts[label] = self._counts.get(label, 0) + 1
        tok = f"[{label}_{self._counts[label]}]"
        self._fwd[original] = tok
        self._rev[tok] = original
        return tok

    def mask(self, text: str) -> str:
        for label, rx in _PATTERNS + self._extra:
            text = rx.sub(lambda m: self._token(label, m.group(0)), text)
        return text

    def unmask(self, text: str) -> str:
        for tok, original in self._rev.items():
            text = text.replace(tok, original)
        return text

    @property
    def map(self) -> dict:
        return dict(self._rev)


if __name__ == "__main__":
    m = Masker()
    sample = ("Acme Holdings LLC (EIN 12-3456789) contributed $245,000; "
              "contact jane@acme.com / 415-555-0199. Partner A took 99% of depreciation.")
    masked = m.mask(sample)
    print("  sent:    ", masked)
    print("  map:     ", m.map)
    print("  restored:", m.unmask(masked))
    assert m.unmask(masked) == sample, "round-trip must be lossless"
    print("  round-trip OK")
