#!/usr/bin/env python3
"""
lawfact.py — the conclusion-of-law vs. conclusion-of-fact distinction, as a standalone,
dependency-free classifier. Drop it into any project.

Grounding: a *conclusion of law* is where the writer stops being a historian (what happened)
and becomes a legal arbiter (the legal consequence of what happened) — applying a legal standard
to facts to reach an outcome. Twombly/Iqbal call out "legal conclusions couched as factual
allegations" and "threadbare recitals ... supported by mere conclusory statements." So the
detector flags text that DETERMINES a legal status/consequence, and passes text that DESCRIBES
facts, history, statistics, or economic/business reality.

It is deliberately CONSERVATIVE: when in doubt it flags (a false "this looks like a legal
conclusion" is cheap; a missed one is not). Used here as the gate that keeps an LLM's
augmentations non-legal — but it stands alone.

    import lawfact
    lawfact.is_conclusion_of_law("Missouri may tax this receipt")          # -> True
    lawfact.classify("Cigarette tax revenue fell 12% from 2019 to 2024")   # -> FACTUAL
"""
from __future__ import annotations

import re

# Legal-outcome predicates applied to a party/transaction → a conclusion of LAW.
# Each entry is (pattern, label-of-what-it-detects). Patterns are matched case-insensitively.
_OUTCOME = re.compile(
    r"\b(?:is|are|was|were|be|becomes?|remains?|will\s+be)\s+"
    r"(?:not\s+)?(?:a\s+|an\s+)?"
    r"(taxable|tax-exempt|exempt|immune|preempted|liable|unconstitutional|constitutional|"
    r"apportionable|deductible|nondeductible|disregarded|respected|valid|invalid|enforceable|"
    r"unenforceable|a\s+sham|substantial)\b",
    re.I,
)
_HAS = re.compile(
    r"\b(?:has|have|had|lacks?|possesses?|establishes?|fails?\s+to\s+(?:establish|have))\s+"
    r"(?:no\s+|a\s+|substantial\s+)*"
    r"(nexus|substantial\s+nexus|economic\s+substance|substantial\s+economic\s+effect|"
    r"economic\s+effect|standing|a\s+business\s+purpose|substantiality)\b",
    re.I,
)
_CONSTITUTES = re.compile(
    r"\b(constitutes?|amounts?\s+to|qualifies?\s+as|is\s+treated\s+as|is\s+characterized\s+as|"
    r"is\s+properly\s+(?:classified|treated))\b",
    re.I,
)
# Normative legal modality — duty/entitlement/obligation.
_MODALITY = re.compile(
    r"\b(must|shall|is\s+required\s+to|are\s+required\s+to|is\s+obligated\s+to|"
    r"is\s+entitled\s+to|are\s+entitled\s+to|owes?|is\s+permitted\s+to|may\s+(?:tax|deduct|exclude))\b",
    re.I,
)
_VIOLATES = re.compile(r"\b(violates?|is\s+in\s+violation\s+of|runs?\s+afoul\s+of|triggers?\s+liability)\b", re.I)
# Domain: the §704(b) ultimate conclusions specifically.
_SEE_CONCLUSION = re.compile(
    r"\b(allocation|distribution)\b[^.]{0,60}\b(has|have|lacks?|will\s+have|does\s+not\s+have)\s+"
    r"(substantial\s+)?economic\s+effect\b", re.I,
)

_SIGNALS = [
    ("outcome_predicate", _OUTCOME),
    ("legal_attribute", _HAS),
    ("legal_characterization", _CONSTITUTES),
    ("normative_modality", _MODALITY),
    ("violation", _VIOLATES),
    ("see_conclusion", _SEE_CONCLUSION),
]

# Phrases that look legal but are DESCRIPTIVE (talking ABOUT the test, not applying it).
# When present, we don't downgrade — we still flag — but they're recorded for transparency.
_DESCRIPTIVE_HINT = re.compile(
    r"\b(the\s+(test|standard|rule|doctrine|requirement|analysis|question)\s+(for|of|is|requires)|"
    r"whether\b|to\s+determine\s+whether|in\s+general|historically|the\s+regulation\s+(provides|defines))",
    re.I,
)


def classify(text: str) -> dict:
    """Return {label, signals, descriptive_hint}. label is 'CONCLUSION_OF_LAW' if any
    legal-outcome signal fires, else 'FACTUAL'. signals lists which markers matched."""
    t = text or ""
    hits = []
    for name, rx in _SIGNALS:
        m = rx.search(t)
        if m:
            hits.append({"signal": name, "match": re.sub(r"\s+", " ", m.group(0)).strip()})
    return {
        "label": "CONCLUSION_OF_LAW" if hits else "FACTUAL",
        "signals": hits,
        "descriptive_hint": bool(_DESCRIPTIVE_HINT.search(t)),
    }


def is_conclusion_of_law(text: str) -> bool:
    return classify(text)["label"] == "CONCLUSION_OF_LAW"


if __name__ == "__main__":
    import sys
    for line in (sys.argv[1:] or [
        "Missouri may tax this receipt.",
        "The partnership's special allocation has substantial economic effect.",
        "Cigarette tax revenue fell 12 percent from 2019 to 2024.",
        "Historically, states adopted market-based sourcing after 2010.",
        "The taxpayer must file Form 1065.",
        "The economic-effect test requires capital accounts to be maintained.",
    ]):
        r = classify(line)
        print(f"  [{r['label']:<18}] {line}")
        if r["signals"]:
            print("      signals:", ", ".join(s["signal"] for s in r["signals"]))
