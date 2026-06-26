#!/usr/bin/env python3
"""
subk_doctrine.py — doctrine registry. Each module exports the same shape (DOCTRINE, ROOT_CITE,
FACTORS, FRAME_FIELDS, REQUIRED_MINIMUM, SCOPE_SIGNALS, PROVISION_PATTERNS, empty_frame,
evaluable, readiness, authority_cites) so the orchestrator can dispatch generically.

This is the entire 'how to add a doctrine' story: import the module, add it to DOCTRINES, done.
"""
from __future__ import annotations

import subk_see
import subk_disguised
import subk_antiabuse

DOCTRINES = {
    subk_see.DOCTRINE: subk_see,                  # "substantial_economic_effect"
    subk_disguised.DOCTRINE: subk_disguised,      # "disguised_sale"
    subk_antiabuse.DOCTRINE: subk_antiabuse,      # "anti_abuse"
}

# Friendly aliases for command-line use.
ALIASES = {
    "see": subk_see.DOCTRINE, "704b": subk_see.DOCTRINE, "economic_effect": subk_see.DOCTRINE,
    "ds": subk_disguised.DOCTRINE, "disguised": subk_disguised.DOCTRINE,
    "707": subk_disguised.DOCTRINE, "1.707-3": subk_disguised.DOCTRINE,
    "aa": subk_antiabuse.DOCTRINE, "antiabuse": subk_antiabuse.DOCTRINE,
    "abuse": subk_antiabuse.DOCTRINE, "701-2": subk_antiabuse.DOCTRINE,
    "1.701-2": subk_antiabuse.DOCTRINE,
}


def resolve(name: str):
    """Resolve 'see' / 'ds' / a full doctrine key into the doctrine module."""
    if not name:
        return None
    n = name.lower().strip()
    n = ALIASES.get(n, n)
    return DOCTRINES.get(n)


def autodetect(text: str):
    """Pick the doctrine whose SCOPE_SIGNALS score highest in `text`. Returns (module, score, scores)."""
    t = (text or "").lower()
    scores = {name: sum(1 for s in mod.SCOPE_SIGNALS if s in t) for name, mod in DOCTRINES.items()}
    best = max(scores, key=scores.get)
    return (DOCTRINES[best], scores[best], scores) if scores[best] > 0 else (None, 0, scores)


def pick_for_form(form: dict):
    """A form's field NAMES are doctrine-specific (e.g. SEE has 'qualified_income_offset'; disguised
    sale has 'transfers_within_two_years'). Pick the doctrine whose FRAME_FIELDS covers the most
    keys in `form`. Returns the module or None on tie/no overlap."""
    if not isinstance(form, dict) or not form:
        return None
    keys = set(form)
    scores = {name: len(keys & set(mod.FRAME_FIELDS)) for name, mod in DOCTRINES.items()}
    best_name = max(scores, key=scores.get)
    sorted_scores = sorted(scores.values(), reverse=True)
    if sorted_scores[0] == 0 or (len(sorted_scores) > 1 and sorted_scores[0] == sorted_scores[1]):
        return None
    return DOCTRINES[best_name]


def names() -> list:
    return list(DOCTRINES)
