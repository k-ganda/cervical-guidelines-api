"""
Severity classifier (v2 build instructions §3.3).

Severity is DERIVED from the signals the cleaned DAK already carries (card_indicator,
execution_status, recommendation_type), then optionally overridden by a rule-admin
config within governance limits. It is NOT configured from scratch — so an admin can
never silently turn a `critical` guideline signal green.

Returns (severity_class, blocking, block_scope).
"""
from __future__ import annotations

# recommendation_types that are system/safety states, not clinical alerts
_GOVERNANCE_TYPES = {
    "binding_unresolved_needs_review", "conflict_detected_needs_clinical_review",
    "blocked_needs_review", "sandbox_withheld_in_production",
}

# the small, enumerated hard-block set (block the specific transition, not the screen)
_BLOCK_SCOPE_BY_ACTION = {
    "create_referral": "close_episode",   # suspected-cancer / urgent referral -> block close until actioned
    "block_treatment": "treatment_action",
    "open_required_form": "continue_workflow",
}
# red alerts with these action codes block by default (audit §4.2) unless config overrides
_RED_BLOCKING_ACTIONS = {"create_referral", "block_treatment", "open_required_form"}


def classify(result, config: dict | None = None, completeness: bool = True):
    """config = optional cds_rule_configs overlay row (dict) with keys enabled,
    severity_class, blocking, safe_fallback. Governance limits enforced here."""
    rt = result.recommendation_type
    indicator = (result.card_indicator or "").lower()
    exec_status = (result.execution_status or "sandbox").lower()

    # 1) system/safety states -> amber governance (never green 'all clear', never red clinical)
    if rt in _GOVERNANCE_TYPES:
        return "amber", False, "none"
    if rt == "insufficient_data":
        return "amber", False, "none"
    if rt != "recommendation":
        return "green", False, "none"

    # 2) blocked execution -> silent (never clinical)
    if exec_status == "blocked":
        return "silent", False, "none"

    # 3) derive from the DAK card indicator
    if indicator == "critical" and completeness:
        severity, blocking = "red", False
    elif indicator == "warning":
        severity, blocking = "amber", False
    else:
        severity, blocking = "green", False

    block_scope = "none"

    # 4) config overlay — may raise severity, or lower ONLY with clinical approval;
    #    may never turn a DAK-critical signal green; sandbox never hard-blocks
    config_forces_blocking = None
    if config:
        if config.get("enabled") is False:
            return "silent", False, "none"
        cfg_sev = (config.get("severity_class") or "").lower()
        if cfg_sev in ("red", "amber", "green", "silent"):
            downgrade = ["silent", "green", "amber", "red"]
            approved = str(config.get("clinical_review_status", "")).lower() == "approved"
            is_downgrade = downgrade.index(cfg_sev) < downgrade.index(severity) if severity in downgrade else False
            if indicator == "critical" and cfg_sev in ("green", "silent"):
                pass  # forbidden: never mute a critical DAK signal
            elif is_downgrade and not approved:
                pass  # downgrades require clinical approval
            else:
                severity = cfg_sev
        if config.get("blocking") is not None:
            config_forces_blocking = bool(config.get("blocking"))

    # 5) blocking: config wins if set; else red + safety-critical action -> block by default
    if severity == "red":
        if config_forces_blocking is not None:
            blocking = config_forces_blocking
        elif result.action_code in _RED_BLOCKING_ACTIONS:
            blocking = True
        if blocking:
            block_scope = _BLOCK_SCOPE_BY_ACTION.get(result.action_code, "close_episode")

    return severity, blocking, block_scope


def snooze_options_for(severity: str) -> list:
    if severity == "red":
        return ["until_encounter_close"]          # red may only be snoozed briefly, with reason
    if severity == "amber":
        return ["until_form_save", "1_hour", "end_of_day", "until_next_visit"]
    return []
