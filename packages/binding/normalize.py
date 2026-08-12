"""
Value normalization (terminology binding, value level).

All 116 decision rules match on free-text values (e.g. "HPV-positive") with no
value_code. Forms may store "Positive", "pos", "hr-HPV detected". Without
normalization, string equality silently fails and the rule never fires.

This module normalizes BOTH the stored fact and the rule's value to a canonical
code before comparison. Value sets are seeded from the data dictionary's
`input_options` where present (78/287 elements) and augmented with a reviewable
synonym map for the concepts that drive triage branches.

Everything here is marked needs_review: the synonym seeds are engineering
scaffolding, not clinically signed-off terminology.
"""
from __future__ import annotations

import re
import unicodedata

# Reviewable synonym seeds for the high-traffic triage concepts. Keyed by a
# canonical code -> list of lowercased synonyms. Extend from field value sets.
#
# IMPORTANT: the GLOBAL index holds only UNAMBIGUOUS, concept-qualified phrases.
# Bare tokens like "positive"/"negative"/"normal" are deliberately NOT here — they
# are ambiguous across concepts (an HPV "positive" is not a VIA "positive") and must
# be resolved through an element-scoped value set that knows the concept. Putting them
# in a global index silently mis-maps facts (a bug we hit and fixed in the demo).
CANONICAL_SYNONYMS: dict[str, list[str]] = {
    "HPV_POS": ["hpv-positive", "hpv positive", "hr-hpv detected"],
    "HPV_NEG": ["hpv-negative", "hpv negative"],
    "HPV_INVALID": ["invalid", "unavailable", "indeterminate", "no result"],
    "VIA_POS": ["via-positive", "via positive"],
    "VIA_NEG": ["via-negative", "via negative"],
    "VIA_TRIAGE": ["via triage", "via as triage", "triage with via"],
    "ELIGIBLE_ABLATION": ["eligible for ablative treatment", "eligible for ablation", "ablation eligible"],
    "NOT_ELIGIBLE_ABLATION": ["not eligible for ablation", "ineligible for ablation",
                              "not eligible for ablative treatment"],
    "SUSPICIOUS_CANCER": ["suspicious for cancer", "suspected cancer", "cancer suspected"],
    # demographics (injected by FactContextBuilder) — concept-qualified, safe globally
    "HIV_POSITIVE": ["hiv positive", "hiv-positive", "positive hiv", "wlhiv", "living with hiv"],
    "HIV_NEGATIVE": ["hiv negative", "hiv-negative", "negative hiv"],
    "HIV_UNKNOWN": ["hiv unknown", "unknown hiv status"],
    "PREGNANT": ["pregnant", "is pregnant", "currently pregnant"],
    "NOT_PREGNANT": ["not pregnant", "non-pregnant", "not currently pregnant"],
    "POSTPARTUM": ["postpartum", "post-partum", "post partum"],
}


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    s = re.sub(r"[\s_]+", " ", s)
    return s


# reverse index: synonym -> canonical code
_SYNONYM_INDEX: dict[str, str] = {}
for code, syns in CANONICAL_SYNONYMS.items():
    for syn in syns:
        _SYNONYM_INDEX[_slug(syn)] = code


class Normalizer:
    """Normalizes raw values to canonical codes. Falls back to a slug so that
    exact (case/space-insensitive) matches still work for concepts we have not
    yet given a synonym set."""

    def __init__(self, value_sets: dict[str, dict] | None = None) -> None:
        # value_sets: element_id -> {raw_value_slug: canonical_code} seeded from input_options
        self.value_sets = value_sets or {}
        self.unmatched: set[str] = set()

    def normalize(self, raw, element_id: str | None = None) -> str | None:
        if raw is None:
            return None
        s = _slug(raw)
        # element-specific value set first
        if element_id and element_id in self.value_sets:
            vs = self.value_sets[element_id]
            if s in vs:
                return vs[s]
        # global synonym index
        if s in _SYNONYM_INDEX:
            return _SYNONYM_INDEX[s]
        # numeric passthrough (ages, counts)
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return s
        # fall back to slug; record that we had no canonical mapping
        self.unmatched.add(s)
        return f"RAW::{s}"

    def values_match(self, fact_raw, rule_raw, element_id: str | None = None) -> bool:
        return self.normalize(fact_raw, element_id) == self.normalize(rule_raw, element_id)


def seed_value_sets_from_dak(dak) -> dict[str, dict]:
    """Build element_id -> {value_slug: code} from data dictionary input_options.
    input_options are free text; we mint provisional codes and slug the labels."""
    out: dict[str, dict] = {}
    for e in dak.elements:
        deid = e.get("data_element_id")
        opts = e.get("input_options")
        if not deid or not opts:
            continue
        # input_options may be a delimited string or a list
        if isinstance(opts, str):
            parts = re.split(r"[;\n|]", opts)
        elif isinstance(opts, list):
            parts = [str(p) for p in opts]
        else:
            continue
        vs = {}
        for p in parts:
            p = p.strip()
            if not p:
                continue
            vs[_slug(p)] = _slug(p).upper().replace(" ", "_")[:40]
        if vs:
            out[deid] = vs
    return out
