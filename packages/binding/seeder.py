"""
Phase 0 (blocking): Concept Binding seeder.

The decision-table rules reference L1 concept ids (KEN-CC-L1-...). The forms capture
data under L2 element ids (CC.A.REG.DE.001). They do not share a key. This module
builds the crosswalk that lets the rule engine bind runtime facts (L2) to rule inputs
(L1), and produces the orphan report that gates the build.

Binding status meanings:
  confirmed_auto        -> exactly one L2 element carries this L1 id; safe to use pending clinical sign-off
  ambiguous_needs_review-> multiple L2 elements carry it; a human must pick the primary
  orphan_needs_mapping  -> no L2 element carries it; rule input is UNBOUND (engine is inert on that path)

Nothing here is treated as clinically final: every auto binding is emitted with
clinical_review_status = "not_started", per the v2 build instructions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

from packages.dak_parser.loader import DAK


@dataclass
class ConceptBinding:
    l1_concept_id: str
    concept_label: str
    primary_l2_element_id: str | None
    candidate_l2_element_ids: list[str]
    binding_status: str
    binding_source: str
    clinical_review_status: str = "not_started"
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class BindingReport:
    bindings: list[ConceptBinding] = field(default_factory=list)
    total_rule_inputs: int = 0
    confirmed: int = 0
    ambiguous: int = 0
    orphans: list[str] = field(default_factory=list)

    @property
    def is_gate_g0_passed(self) -> bool:
        # G0 requires every rule-input concept to be confirmed (auto counts as
        # seeded-but-not-signed-off; true gate also needs clinical sign-off).
        return not self.orphans and self.ambiguous == 0

    def index(self) -> dict[str, ConceptBinding]:
        return {b.l1_concept_id: b for b in self.bindings}


def concept_metadata(dak: DAK) -> dict[str, dict]:
    """concept_id -> {label, sample_values, tables} derived from how each concept is
    actually used as a decision-table input. This makes orphan hashes human-readable
    and shows the reviewer the values the rules match against."""
    meta: dict[str, dict] = {}
    for tbl_name, rows in dak.decision_tables.items():
        clean_tbl = tbl_name.split(" ", 1)[-1] if " " in tbl_name else tbl_name
        for r in rows:
            for i in ("input_1", "input_2", "input_3", "input_4"):
                inp = r.get(i)
                if not isinstance(inp, dict) or not inp.get("data_element_id"):
                    continue
                cid = inp["data_element_id"]
                m = meta.setdefault(cid, {"tables": set(), "sample_values": []})
                m["tables"].add(clean_tbl)
                v = inp.get("value")
                if v is not None and v not in m["sample_values"] and len(m["sample_values"]) < 6:
                    m["sample_values"].append(v)

    # attach a human label: prefer an agreed candidate L2 label; else infer from usage
    crosswalk = dak.element_l1_crosswalk()
    l1_to_l2: dict[str, list[str]] = {}
    for l2, l1s in crosswalk.items():
        for l1 in l1s:
            l1_to_l2.setdefault(l1, []).append(l2)

    for cid, m in meta.items():
        labels = set()
        for l2 in l1_to_l2.get(cid, []):
            el = dak.element_by_id.get(l2)
            if el and el.get("data_element_label"):
                labels.add(el["data_element_label"])
        if len(labels) == 1:
            m["label"] = next(iter(labels))
        elif m["sample_values"]:
            vals = ", ".join(str(v) for v in m["sample_values"][:3])
            m["label"] = f"{list(m['tables'])[0]} input — e.g. {vals}"
        elif labels:
            m["label"] = sorted(labels)[0]
        else:
            m["label"] = cid
        m["tables"] = sorted(m["tables"])
    return meta


def resolve_binding(report: "BindingReport", l1_concept_id: str,
                    l2_element_id: str, reviewer: str = "unspecified") -> bool:
    """Apply a reviewer's decision to bind an orphan/ambiguous concept to a
    specific L2 element. This is the Phase-0 human action the gate waits for.
    Returns True if a binding was updated."""
    for b in report.bindings:
        if b.l1_concept_id == l1_concept_id:
            was_orphan = b.binding_status.startswith("orphan")
            was_ambiguous = b.binding_status.startswith("ambiguous")
            b.primary_l2_element_id = l2_element_id
            if l2_element_id not in b.candidate_l2_element_ids:
                b.candidate_l2_element_ids.append(l2_element_id)
            b.binding_status = "confirmed_manual"
            b.binding_source = f"manual:{reviewer}"
            b.notes = f"Resolved by {reviewer}. Pending clinical sign-off."
            if was_orphan and l1_concept_id in report.orphans:
                report.orphans.remove(l1_concept_id)
            if was_ambiguous:
                report.ambiguous = max(0, report.ambiguous - 1)
            report.confirmed += 1
            return True
    return False


def _label_for(dak: DAK, l1_id: str, l2_candidates: list[str]) -> str:
    # Prefer a clean L2 element label; fall back to the L1 rec label.
    for c in l2_candidates:
        el = dak.element_by_id.get(c)
        if el and el.get("data_element_label"):
            return el["data_element_label"]
    for rec in dak.l1_recommendations:
        if l1_id in str(rec.values()):
            return (rec.get("recommendation_summary")
                    or rec.get("statement")
                    or rec.get("recommendation")
                    or l1_id)
    return l1_id


def seed_bindings(dak: DAK) -> BindingReport:
    rule_inputs = dak.rule_input_concepts()
    crosswalk = dak.element_l1_crosswalk()  # L2 -> {L1}

    # invert: L1 -> [L2]
    l1_to_l2: dict[str, list[str]] = {}
    for l2, l1s in crosswalk.items():
        for l1 in l1s:
            l1_to_l2.setdefault(l1, []).append(l2)

    report = BindingReport(total_rule_inputs=len(rule_inputs))
    l2_ids = set(dak.element_by_id.keys())
    for l1 in sorted(rule_inputs):
        # identity binding: cleaned DAK sometimes uses an L2 element id directly as a
        # rule input; it binds to itself.
        if l1 in l2_ids:
            el = dak.element_by_id.get(l1, {})
            report.bindings.append(ConceptBinding(
                l1_concept_id=l1, concept_label=el.get("data_element_label") or l1,
                primary_l2_element_id=l1, candidate_l2_element_ids=[l1],
                binding_status="confirmed_auto",
                binding_source="identity_l2_element",
                notes="Rule input is itself a captured L2 element (direct binding).",
            ))
            report.confirmed += 1
            continue
        cands = sorted(set(l1_to_l2.get(l1, [])))
        label = _label_for(dak, l1, cands)
        if len(cands) == 1:
            report.bindings.append(ConceptBinding(
                l1_concept_id=l1, concept_label=label,
                primary_l2_element_id=cands[0], candidate_l2_element_ids=cands,
                binding_status="confirmed_auto",
                binding_source="seeded_from_source_recommendation_id",
                notes="Single L2 element carries this concept; confirm before production.",
            ))
            report.confirmed += 1
        elif len(cands) > 1:
            report.bindings.append(ConceptBinding(
                l1_concept_id=l1, concept_label=label,
                primary_l2_element_id=None, candidate_l2_element_ids=cands,
                binding_status="ambiguous_needs_review",
                binding_source="seeded_from_source_recommendation_id",
                notes=f"{len(cands)} candidate L2 elements; a reviewer must pick the primary.",
            ))
            report.ambiguous += 1
        else:
            report.bindings.append(ConceptBinding(
                l1_concept_id=l1, concept_label=label,
                primary_l2_element_id=None, candidate_l2_element_ids=[],
                binding_status="orphan_needs_mapping",
                binding_source="none",
                notes="No L2 element carries this concept. Rule inputs on this path are "
                      "UNBOUND; engine returns binding_unresolved_needs_review until mapped.",
            ))
            report.orphans.append(l1)
    return report
