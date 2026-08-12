"""
CDS Control Centre service (plan §7). Turns curated recommendation dicts into persisted
CdsRecommendationState rows (so accept/dismiss/snooze/override work), applies the admin
overlay (severity, blocking, card text, trigger modes, action override, cooldown), enforces
trigger-mode filtering, and runs the high-risk-change draft workflow.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages import curated_cds
from packages.persistence import models as m
from packages.persistence import repository as repo

# event_type -> required trigger mode (plan §7.4)
EVENT_TO_TRIGGER = {
    "field_change": "push", "manual": "manual", "module_complete": "manual",
    "save_after": "save_after", "close_check": "close_check",
    "background_review": "background", "pull": "pull_only",
    "section_enter": "on_enter_section", "action_accepted": "on_action_accepted",
}
DEFAULT_TRIGGER_MODES = ["push", "manual", "close_check"]

# changes that must go through draft review (plan §7.5, §9)
HIGH_RISK = {
    "disable_red_rule", "downgrade_red_severity", "disable_red_blocking",
    "change_action_code_from_referral", "change_clinical_logic", "change_value_set",
    "change_followup_interval", "change_required_fields",
}


def _catalog_rule(rule_id):
    return next((r for r in curated_cds.catalog().get("rules", []) if r["rule_id"] == rule_id), None)


def config_for(db: Session, rule_id: str):
    return db.scalar(select(m.CuratedCdsRuleConfig).where(m.CuratedCdsRuleConfig.rule_id == rule_id))


def trigger_modes(db: Session, rule_id: str) -> list:
    cfg = config_for(db, rule_id)
    if cfg and cfg.trigger_modes:
        return cfg.trigger_modes
    cat = _catalog_rule(rule_id)
    return (cat or {}).get("trigger_mode", DEFAULT_TRIGGER_MODES)


def should_run(db: Session, rule_id: str, event_type: str) -> bool:
    required = EVENT_TO_TRIGGER.get(event_type, "manual")
    modes = trigger_modes(db, rule_id)
    if event_type == "pull" and "manual" in modes:
        return True
    return required in modes


def evaluate_and_persist(db: Session, *, facts: dict, patient_id=None, episode_id=None,
                         event_type="manual", county=None) -> list[dict]:
    """Evaluate curated rules, apply admin overlay + trigger filtering + cooldown, and
    persist a CdsRecommendationState per shown recommendation (plan §7.3). No side effects."""
    recs = curated_cds.evaluate(facts)
    cfgs = {c.rule_id: c for c in db.scalars(select(m.CuratedCdsRuleConfig)).all()}
    out = []
    now = datetime.utcnow()
    for rec in recs:
        rid = rec["rule_id"]
        cfg = cfgs.get(rid)
        if cfg and not cfg.enabled:
            continue
        if not should_run(db, rid, event_type):
            continue
        # county scope
        if cfg and cfg.county_scope and county and county not in cfg.county_scope:
            continue
        # apply admin overlay
        if cfg:
            if cfg.severity_override:
                rec["severity_class"] = cfg.severity_override
            if cfg.blocking_override is not None:
                rec["blocking"] = cfg.blocking_override
            if cfg.card_title:
                rec["recommendation_text"] = cfg.card_title
            if cfg.card_summary:
                rec["reason_text"] = cfg.card_summary
            if cfg.action_code_override and cfg.action_code_override != rec.get("action_code"):
                # §14: only apply an action-code override if the payload is compatible with it;
                # otherwise the deterministic action stands (a mismatched override would produce a
                # nonsensical side effect, e.g. create_referral executing from a schedule payload).
                violations = curated_cds.validate_action_contract(cfg.action_code_override, rec.get("action_payload"))
                if not violations:
                    rec["action_code"] = cfg.action_code_override
                else:
                    rec.setdefault("_policy_notes", []).append(
                        f"action_code_override '{cfg.action_code_override}' ignored: incompatible payload")
        # cooldown: suppress a repeat of the same rule within cooldown window
        if cfg and cfg.cooldown_minutes and episode_id:
            recent = db.scalars(select(m.CdsRecommendationState).where(
                m.CdsRecommendationState.episode_id == episode_id,
                m.CdsRecommendationState.rule_id == rid,
                m.CdsRecommendationState.status.in_(["shown", "snoozed", "dismissed"]))).all()
            if any(r.shown_at and r.shown_at > now - timedelta(minutes=cfg.cooldown_minutes) for r in recent):
                continue
        persisted = _persist(db, rec, patient_id=patient_id, episode_id=episode_id, cfg=cfg)
        if persisted:
            out.append(persisted)
    return out


def _fingerprint(rec: dict, episode_id) -> str:
    import hashlib
    payload = {"rule_id": rec["rule_id"], "episode_id": episode_id,
               "facts_used": rec.get("facts_used") or {},
               "action_payload": rec.get("action_payload") or {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _persist(db: Session, rec: dict, *, patient_id, episode_id, cfg) -> dict | None:
    fp = _fingerprint(rec, episode_id)
    now = datetime.utcnow()
    existing = db.scalars(select(m.CdsRecommendationState).where(
        m.CdsRecommendationState.source_facts_hash == fp,
        m.CdsRecommendationState.status.in_(["shown", "snoozed"]))).first()
    if existing:
        # §12: an actively snoozed card is suppressed until the snooze expires
        if existing.status == "snoozed":
            if existing.snoozed_until and existing.snoozed_until > now:
                return None
            existing.status = "shown"
            existing.snoozed_until = None
        return _card(existing, rec, cfg)
    # P0.2 / P0.19: a COMPLETED fingerprint (accepted/overridden) for unchanged facts must NOT be
    # recreated — that caused duplicate appointments and the red-modal reappearance loop.
    completed = db.scalars(select(m.CdsRecommendationState).where(
        m.CdsRecommendationState.source_facts_hash == fp,
        m.CdsRecommendationState.status.in_(["accepted", "overridden"]))).first()
    if completed:
        return None  # already handled for this exact clinical state
    # dismissed: respect cooldown/reappearance policy — suppress unless cooldown elapsed
    dismissed = db.scalars(select(m.CdsRecommendationState).where(
        m.CdsRecommendationState.source_facts_hash == fp,
        m.CdsRecommendationState.status == "dismissed").order_by(
        m.CdsRecommendationState.id.desc())).first()
    if dismissed:
        cd = (cfg.cooldown_minutes if cfg and cfg.cooldown_minutes else None)
        if cd is None:
            return None  # no cooldown configured => stay dismissed for unchanged facts
        ref_t = getattr(dismissed, "dismissed_at", None) or getattr(dismissed, "shown_at", None)
        if ref_t and ref_t > datetime.utcnow() - timedelta(minutes=cd):
            return None
    # supersede any stale active recommendation from the SAME rule with a different fingerprint (plan §1.4)
    if episode_id:
        stale = db.scalars(select(m.CdsRecommendationState).where(
            m.CdsRecommendationState.episode_id == episode_id,
            m.CdsRecommendationState.rule_id == rec["rule_id"],
            m.CdsRecommendationState.status.in_(["shown", "snoozed"]),
            m.CdsRecommendationState.source_facts_hash != fp)).all()
        for s in stale:
            s.status = "resolved"
            s.resolved_at = datetime.utcnow() if hasattr(s, "resolved_at") else None
            repo.write_audit(db, event_type="cds.curated.superseded", object_type="cds_recommendation",
                             object_id=s.id, patient_id=patient_id,
                             new_value={"rule": rec["rule_id"], "reason": "facts changed; recommendation superseded"})
    row = m.CdsRecommendationState(
        patient_id=patient_id, episode_id=episode_id, rule_id=rec["rule_id"],
        decision_table_id=rec.get("workflow_step"), severity_class=rec["severity_class"],
        blocking=rec.get("blocking", False),
        block_scope="encounter" if rec.get("blocking") else "none",
        recommendation_text=(rec.get("recommendation_text") or "")[:500],
        reason_text=(rec.get("reason_text") or "")[:800], action_code=rec.get("action_code", "no_action_required"),
        status="shown", source_facts_hash=fp, guideline_page_refs=rec.get("guideline_page_refs"),
        cds_output=rec)
    db.add(row)
    repo.write_audit(db, event_type="cds.curated.shown", object_type="cds_recommendation",
                     object_id=row.id, patient_id=patient_id,
                     new_value={"rule": rec["rule_id"], "severity": rec["severity_class"]})
    db.commit()
    if cfg and cfg.safe_auto and rec["severity_class"] != "red":
        from apps.api import recommendations as recs_lifecycle
        recs_lifecycle.accept(db, {"dak": None}, row.id, user_id="system:safe_auto")
    return _card(row, rec, cfg)


def _card(row, rec, cfg) -> dict:
    return {"recommendation_id": row.id, "rule_id": rec["rule_id"],
            "decision_point_id": (_catalog_rule(rec["rule_id"]) or {}).get("primary_input"),
            "severity_class": row.severity_class, "blocking": row.blocking,
            "action_code": row.action_code, "recommendation_text": row.recommendation_text,
            "card_title": row.recommendation_text, "card_summary": row.reason_text,
            "reason_text": row.reason_text,
            "dismissal_allowed": (cfg.dismissal_allowed if cfg else True) and row.severity_class != "red",
            "override_allowed": (cfg.override_allowed if cfg else True),
            "trigger_modes": cfg.trigger_modes if (cfg and cfg.trigger_modes) else DEFAULT_TRIGGER_MODES,
            "guideline_page_refs": row.guideline_page_refs or [],
            "admin_config_version": (cfg.version if cfg else 1), "status": row.status,
            "cds_output": row.cds_output}


# ------------------------------------------------------- decision points
def sync_decision_points(db: Session):
    """Upsert EVERY catalog rule input (primary + dependent + required) into the decision-point
    registry with role + persistence-source metadata (§9). Upgrade-safe: adds new inputs without
    resetting the table, updates used_by_rules, and marks removed inputs inactive."""
    import json as _json
    from pathlib import Path as _P
    from packages import cds_facts
    wf = _json.loads((_P(__file__).resolve().parents[2] / "data" / "curated_workflow" / "workflow.json").read_text())
    field_index = {}
    for s in wf["steps"]:
        for sec in (s.get("sections", []) + s.get("subsections", [])):
            for f in sec.get("fields", []):
                field_index[f["id"]] = {"label": f.get("label"), "step": s["id"],
                                        "section": sec.get("name") or sec.get("key"),
                                        "values": f.get("values"), "labels": f.get("value_labels")}
    cat = curated_cds.catalog()
    cat_version = cat.get("catalog_version")
    roles, used_by = {}, {}
    for r in cat.get("rules", []):
        rid = r["rule_id"]
        prim = r.get("primary_input")
        if prim:
            roles.setdefault(prim, set()).add("primary"); used_by.setdefault(prim, set()).add(rid)
        for dep in (r.get("dependent_inputs") or []):
            roles.setdefault(dep, set()).add("dependent"); used_by.setdefault(dep, set()).add(rid)
        for req in (r.get("required_inputs") or []):
            roles.setdefault(req, set()).add("required"); used_by.setdefault(req, set()).add(rid)
    existing = {d.decision_point_id: d for d in db.scalars(select(m.CuratedCdsDecisionPoint)).all()}
    seen = set()
    for dp, role_set in roles.items():
        seen.add(dp)
        meta = field_index.get(dp, {})
        role = "primary" if "primary" in role_set else ("required" if "required" in role_set else "dependent")
        binding = cds_facts.field_binding(dp)
        rules_list = sorted(used_by.get(dp, []))
        row = existing.get(dp)
        if row:
            row.used_by_rules = rules_list
            row.workflow_step = row.workflow_step or meta.get("step")
            row.section = row.section or meta.get("section")
            if not row.allowed_values and meta.get("values"):
                row.allowed_values = meta.get("values")
            row.active = True
            if hasattr(row, "role"):
                row.role = role
            if hasattr(row, "persistence_source"):
                row.persistence_source = binding
            if hasattr(row, "catalog_version"):
                row.catalog_version = cat_version
        else:
            kwargs = dict(decision_point_id=dp, label=meta.get("label", dp), workflow_step=meta.get("step"),
                          section=meta.get("section"), canonical_field_id=dp, allowed_values=meta.get("values"),
                          value_labels=meta.get("labels"), used_by_rules=rules_list,
                          review_status="clinically_reviewed", active=True, protected=(role == "primary"))
            for opt, val in [("role", role), ("persistence_source", binding), ("catalog_version", cat_version)]:
                if hasattr(m.CuratedCdsDecisionPoint, opt):
                    kwargs[opt] = val
            db.add(m.CuratedCdsDecisionPoint(**kwargs))
    # mark inputs no longer referenced as inactive (preserve the row + review history)
    for dp, row in existing.items():
        if dp not in seen and row.active:
            row.active = False
    db.commit()


def seed_decision_points(db: Session):
    """Back-compat shim — always syncs (§9)."""
    sync_decision_points(db)


def list_decision_points(db: Session) -> list[dict]:
    sync_decision_points(db)
    out = []
    for d in db.scalars(select(m.CuratedCdsDecisionPoint)).all():
        row = {"decision_point_id": d.decision_point_id, "label": d.label, "workflow_step": d.workflow_step,
               "section": d.section, "allowed_values": d.allowed_values or [], "value_labels": d.value_labels or {},
               "used_by_rules": d.used_by_rules or [], "review_status": d.review_status,
               "active": d.active, "protected": d.protected}
        for opt in ("role", "persistence_source", "catalog_version"):
            if hasattr(d, opt):
                row[opt] = getattr(d, opt)
        out.append(row)
    return out


# ------------------------------------------------------- high-risk classification
def classify_change(db: Session, rule_id: str, patch: dict) -> list[str]:
    """Return the list of high-risk change types a patch would trigger (plan §9)."""
    cat = _catalog_rule(rule_id) or {}
    cur = config_for(db, rule_id)
    cur_sev = (cur.severity_override if cur and cur.severity_override else None)
    default_red = "red" in (str(cat.get("default_severity", "")).lower())  # best-effort
    flags = []
    if patch.get("enabled") is False and (cur_sev == "red" or _rule_is_red(rule_id)):
        flags.append("disable_red_rule")
    if patch.get("severity_override") in ("amber", "green", "silent") and _rule_is_red(rule_id):
        flags.append("downgrade_red_severity")
    if patch.get("blocking_override") is False and _rule_is_red(rule_id):
        flags.append("disable_red_blocking")
    if patch.get("action_code_override") and _rule_action_is_referral(rule_id) and patch["action_code_override"] != "create_referral":
        flags.append("change_action_code_from_referral")
    return flags


def _rule_is_red(rule_id: str) -> bool:
    # rules that can produce a red output in the curated logic
    return rule_id in {"cc.via.interpretation", "cc.histology.interpretation",
                       "cc.colposcopy.interpretation", "cc.eligibility.exclusions"}


def _rule_action_is_referral(rule_id: str) -> bool:
    return rule_id in {"cc.via.interpretation", "cc.histology.interpretation",
                       "cc.colposcopy.interpretation", "cc.cytology.interpretation",
                       "cc.eligibility.exclusions"}
