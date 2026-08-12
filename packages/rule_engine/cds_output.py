"""The CDS output contract (v2 build instructions §5.3).

This is the machine-readable object every CDS evaluation returns. It is the ONLY
thing the LLM layer is allowed to read alongside structured facts, and it is what
the CDS Hooks card layer renders. It always carries the rule id, source and
explanation so a clinician can see why.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SOURCE_DOC = ("Kenya National Cancer Screening and Early Diagnosis Guidelines - "
              "Cervical Cancer, MoH Kenya, 2nd ed., 2024")

# sentinel recommendation_types the engine can return
INSUFFICIENT_DATA = "insufficient_data"
BINDING_UNRESOLVED = "binding_unresolved_needs_review"
CONFLICT = "conflict_detected_needs_clinical_review"
NO_MATCH = "no_matching_rule"
SANDBOX_WITHHELD = "sandbox_withheld_in_production"
BLOCKED = "blocked_needs_review"
RULE_DISABLED = "rule_disabled"
RULE_NONCOMPUTABLE = "rule_noncomputable_local_workflow"
OK = "recommendation"


def is_actionable_cds_result(result) -> bool:
    """Single source of truth for whether a result may drive side effects / alerts /
    execution logs (audit §3.3). Disabled, silent, withheld, blocked, insufficient,
    binding-unresolved and no-action results are NOT actionable."""
    if result.recommendation_type != OK:
        return False
    if (result.execution_status or "").lower() in ("blocked", "withheld", "disabled"):
        return False
    if result.severity_class == "silent":
        return False
    if result.action_code in (None, "no_action_required"):
        return False
    return True


@dataclass
class FactUsed:
    l1_concept_id: str
    l2_element_id: str | None
    raw_value: Any
    normalized_code: str | None


@dataclass
class CDSResult:
    patient_id: str = ""
    encounter_id: str = ""
    decision_table_id: str = ""
    rule_id: str = ""
    rule_version: str = ""
    hit_policy: str = ""
    source_document: str = SOURCE_DOC
    dak_artifact: str = "06_decision_support_scheduling"
    input_facts_used: list[FactUsed] = field(default_factory=list)
    missing_required_facts: list[str] = field(default_factory=list)
    missing_for_next_step: list[str] = field(default_factory=list)   # scoped, clinician-actionable
    unbound_concepts: list[str] = field(default_factory=list)
    recommendation_type: str = ""       # OK | insufficient_data | binding_unresolved... | conflict | no_matching_rule
    recommendation: str = ""
    action: str = ""
    urgency: str = "routine"            # routine | urgent | critical
    output_type: str = ""
    schedule_created: dict | None = None
    explanation_for_clinician: str = ""
    explanation_for_client: str = ""
    alert_text: str | None = None
    clinical_review_status: str = "not_started"
    technical_review_status: str = "not_started"
    execution_status: str = "sandbox"      # validated | sandbox | blocked
    card_indicator: str | None = None      # info | warning | critical (from DAK cds_hooks)
    linked_l1_recommendation_ids: list = field(default_factory=list)
    unresolved_l1_references: list = field(default_factory=list)
    clinician_override_allowed: bool = True
    override_requires_reason: bool = True
    provenance: dict = field(default_factory=dict)
    audit_log_id: str = ""
    # --- push-CDS / alert-fatigue / action layer (v2 build instructions §3,§6,§10) ---
    action_code: str = "no_action_required"   # create_referral|schedule_followup|treatment|open_form|block_treatment|show_guideline|document_counselling|add_worklist_item|no_action_required
    severity_class: str = "green"             # red | amber | green | silent
    blocking: bool = False
    block_scope: str = "none"                 # save_result | save_treatment | close_episode | none
    alert_fingerprint: str = ""
    cooldown_policy: str = "default"
    snooze_options: list = field(default_factory=list)
    field_targets: list = field(default_factory=list)          # L2 elements/sections to highlight
    resolution_requirements: list = field(default_factory=list)
    guideline_page_refs: list = field(default_factory=list)
    llm_explanation_allowed: bool = True

    def as_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def is_actionable(self) -> bool:
        return self.recommendation_type == OK
