"""
Compile DAK DMN-style decision tables into an executable internal representation.

Handles the real-world messiness found in the DAK:
  * hit policies come as 'U' / 'UNIQUE' / 'Unique' / 'FIRST' -> normalized
  * multiple inputs in a rule row are AND-grouped (standard DMN semantics)
  * 67/116 rules have zero parseable input conditions -> compiled as `is_default`
    rows and flagged; the engine will NOT silently fire an unconditional rule under
    UNIQUE policy (it surfaces a compile/eval warning instead).
"""
from __future__ import annotations

from dataclasses import dataclass, field

_HIT_POLICY_MAP = {
    "u": "UNIQUE", "unique": "UNIQUE",
    "first": "FIRST",
    "p": "PRIORITY", "priority": "PRIORITY",
    "a": "ANY", "any": "ANY",
    "c": "COLLECT", "collect": "COLLECT",
}

def _as_bool(v, default=True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "1")


def _derive_action_code(row: dict) -> str:
    """Derive a structured action code ONCE at compile time so the runtime never
    has to string-match action text (v2 build instructions §9.3)."""
    text = " ".join(str(row.get(k) or "") for k in ("output", "action", "output_type")).lower()
    if "refer" in text:
        return "create_referral"
    if any(k in text for k in ("rescreen", "re-screen", "return to", "repeat screen",
                               "follow-up", "follow up", "retest", "screen again", "recall")):
        return "schedule_followup"
    if any(k in text for k in ("ablat", "leep", "cryo", "thermal", "treat")):
        return "treatment"
    if "counsel" in text:
        return "document_counselling"
    return "no_action_required"


def _validate_rule(row: dict, conds) -> list[str]:
    """Compile-time validation pass (v2 build instructions §9.2). Non-fatal: findings
    are surfaced on the governance/rule-admin page rather than crashing the load."""
    errors: list[str] = []
    for c in conds:
        op = getattr(c, "operator", "=")
        val = getattr(c, "value", None)
        if op in (">", ">=", "<", "<=") and val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                errors.append(f"numeric operator '{op}' on non-numeric value '{val}' "
                              f"(concept {getattr(c, 'l1_concept_id', '?')})")
    return errors


_VALID_OPERATORS = {"=", "!=", ">", ">=", "<", "<="}


@dataclass
class Condition:
    l1_concept_id: str
    operator: str
    value: str | None
    value_code: str | None
    logical_group: str | None


@dataclass
class CompiledRule:
    rule_id: str
    rule_order: int
    conditions: list[Condition]
    output: str
    action: str
    guidance: str
    alert_text: str | None
    output_type: str
    linked_l1_recommendation_ids: list[str]
    clinical_review_status: str
    technical_review_status: str
    provenance: dict
    is_default: bool = False            # zero-condition row
    compile_warnings: list[str] = field(default_factory=list)
    # cleaned CDS-ready DAK fields (absent on legacy DAK -> safe defaults)
    cds_hooks: dict = field(default_factory=dict)
    cds_executable: bool = True
    unresolved_l1_references: list = field(default_factory=list)
    legacy_l1_recommendation_ids: list = field(default_factory=list)
    action_code: str = "no_action_required"
    safe_fallback: bool = False            # a default row fires clinically ONLY if True
    validation_errors: list = field(default_factory=list)


@dataclass
class CompiledTable:
    decision_id: str
    decision_name: str
    hit_policy: str
    trigger: str
    purpose: str
    clinical_review_status: str
    technical_review_status: str
    provenance: dict
    rules: list[CompiledRule]
    input_concepts: list[str]
    compile_warnings: list[str] = field(default_factory=list)


def _norm_hit_policy(raw: str | None, rule_rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for r in rule_rows:
        hp = _HIT_POLICY_MAP.get(str(r.get("hit_policy_indicator", "")).strip().lower())
        if hp:
            counts[hp] = counts.get(hp, 0) + 1
    if counts:
        return max(counts, key=counts.get)  # most common declared policy in the table
    return "UNIQUE"


def _compile_conditions(row: dict) -> tuple[list[Condition], list[str]]:
    conds: list[Condition] = []
    warns: list[str] = []
    for i in ("input_1", "input_2", "input_3", "input_4"):
        inp = row.get(i)
        if not isinstance(inp, dict):
            continue
        deid = inp.get("data_element_id")
        op = (inp.get("operator") or "=").strip()
        if op not in _VALID_OPERATORS:
            warns.append(f"unknown operator '{op}' in {i}; defaulting to '='")
            op = "="
        if not deid:
            continue
        conds.append(Condition(
            l1_concept_id=deid, operator=op,
            value=inp.get("value"), value_code=inp.get("value_code"),
            logical_group=str(inp.get("logical_group")) if inp.get("logical_group") is not None else None,
        ))
    return conds, warns


def compile_table(register_row: dict, rule_rows: list[dict]) -> CompiledTable:
    hit_policy = _norm_hit_policy(register_row.get("hit_policy_indicator"), rule_rows)
    compiled_rules: list[CompiledRule] = []
    input_concepts: set[str] = set()
    table_warnings: list[str] = []

    for row in sorted(rule_rows, key=lambda r: r.get("rule_order") or 0):
        conds, cwarns = _compile_conditions(row)
        for c in conds:
            input_concepts.add(c.l1_concept_id)
        is_default = len(conds) == 0
        if is_default:
            cwarns.append("zero-condition rule: treated as default/otherwise row and "
                          "surfaced for review; not auto-fired unless marked safe_fallback")
        action_code = _derive_action_code(row)
        v_errors = _validate_rule(row, conds)
        compiled_rules.append(CompiledRule(
            rule_id=row.get("rule_id", ""),
            rule_order=row.get("rule_order") or 0,
            conditions=conds,
            output=row.get("output") or "",
            action=row.get("action") or "",
            guidance=row.get("guidance") or "",
            alert_text=row.get("annotation_s_alert_text"),
            output_type=(row.get("output_type") or "").strip().lower(),
            linked_l1_recommendation_ids=row.get("linked_l1_recommendation_ids") or [],
            clinical_review_status=row.get("clinical_review_status", "not_started"),
            technical_review_status=row.get("technical_review_status", "not_started"),
            provenance=(row.get("_provenance") or [{}])[0] if row.get("_provenance") else {},
            is_default=is_default,
            compile_warnings=cwarns + v_errors,
            cds_hooks=row.get("cds_hooks") if isinstance(row.get("cds_hooks"), dict) else {},
            cds_executable=_as_bool(row.get("cds_executable"), default=True),
            unresolved_l1_references=row.get("unresolved_l1_references") or [],
            legacy_l1_recommendation_ids=row.get("legacy_l1_recommendation_ids") or [],
            action_code=action_code,
            safe_fallback=_as_bool(row.get("safe_fallback"), default=False),
            validation_errors=v_errors,
        ))

    n_default = sum(1 for r in compiled_rules if r.is_default)
    if n_default:
        table_warnings.append(f"{n_default}/{len(compiled_rules)} rules have no input conditions")

    return CompiledTable(
        decision_id=register_row.get("decision_id", ""),
        decision_name=register_row.get("decision_name", ""),
        hit_policy=hit_policy,
        trigger=register_row.get("trigger", ""),
        purpose=register_row.get("purpose_business_rule", ""),
        clinical_review_status=register_row.get("clinical_review_status", "not_started"),
        technical_review_status=register_row.get("technical_review_status", "not_started"),
        provenance=(register_row.get("_provenance") or [{}])[0] if register_row.get("_provenance") else {},
        rules=compiled_rules,
        input_concepts=sorted(input_concepts),
        compile_warnings=table_warnings,
    )


def compile_all(dak) -> dict[str, CompiledTable]:
    """Compile every decision table. Register rows and rule sheets are keyed by
    worksheet_name in the DAK; join them on that."""
    by_worksheet = {r.get("worksheet_name"): r for r in dak.decision_table_register}
    by_id = {r.get("decision_id"): r for r in dak.decision_table_register}
    tables: dict[str, CompiledTable] = {}
    for worksheet_name, rule_rows in dak.decision_tables.items():
        reg = by_worksheet.get(worksheet_name)
        if reg is None:
            # worksheet names look like 'CC.DT.03 HPV result'; recover the id
            did = worksheet_name.split(" ")[0]
            reg = by_id.get(did, {"decision_id": did, "decision_name": worksheet_name})
        ct = compile_table(reg, rule_rows)
        tables[ct.decision_id] = ct
    return tables
