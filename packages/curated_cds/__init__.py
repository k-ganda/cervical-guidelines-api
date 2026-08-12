"""
Curated CDS (v0.7.5). Deterministic clinical authority. Every rule returns the structured
action contract: severity/text/action_code + facts_used + action_payload (schedule / referral
prefill / form prefill). Scheduling uses real calendar arithmetic (dateutil.relativedelta),
never 365*N days. The LLM never changes these outcomes.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

try:
    from dateutil.relativedelta import relativedelta
except Exception:  # pragma: no cover
    relativedelta = None

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "curated_cds" / "cds_catalog.json"

HPV_RESCREEN = "Routine cervical cancer rescreening — HPV"


# ---------------------------------------------------------------- primitives
def normalize_yes_no_unknown(v) -> str:
    s = str(v or "").strip().lower()
    if s in ("yes", "true", "1", "positive", "present"):
        return "yes"
    if s in ("no", "false", "0", "negative", "absent"):
        return "no"
    return "unknown"


def _is_unknown(value) -> bool:
    """Canonical 'missing or explicitly unknown' predicate used by every CDS eligibility gate.
    An explicit UI value of 'unknown' (or empty/not-recorded) counts as missing information — it
    must NEVER be treated as a known-negative that satisfies an exclusion gate (review P0.2/P0.3)."""
    if value is None:
        return True
    return str(value).strip().lower() in {"", "unknown", "not_known", "notknown",
                                          "not_recorded", "notrecorded", "unspecified", "nan"}


def _d(x):
    try:
        return datetime.fromisoformat(str(x)[:10]).date()
    except Exception:
        return None


def add_interval(base: date, value: int, unit: str) -> date:
    if relativedelta:
        if unit == "years":
            return base + relativedelta(years=value)
        if unit == "months":
            return base + relativedelta(months=value)
        if unit == "weeks":
            return base + relativedelta(weeks=value)
        if unit == "days":
            return base + relativedelta(days=value)
    from datetime import timedelta
    days = {"years": 365, "months": 30, "weeks": 7, "days": 1}.get(unit, 1) * value
    return base + timedelta(days=days)


def months_between(a: date, b: date) -> int:
    if not a or not b:
        return 0
    return (b.year - a.year) * 12 + (b.month - a.month)


# ---------------------------------------------------------------- action helpers
def _rec(severity, title, action_code, detail, *, facts_used=None, action_payload=None,
         blocking=False):
    return {"severity_class": severity, "recommendation_text": title, "action_code": action_code,
            "reason_text": detail, "blocking": blocking,
            "block_scope": "encounter" if blocking else "none",
            "facts_used": facts_used or {}, "action_payload": action_payload or {}}


def schedule_action(*, step, section, service_name, interval_value, interval_unit,
                    base_date, base_date_source, reason, prepare_reminders=True):
    """Build a schedule action_payload with a resolved due date, or None if the base date is
    missing (caller converts to open_required_form; never silently uses today for a real schedule)."""
    bd = _d(base_date)
    if not bd:
        return None
    due = add_interval(bd, interval_value, interval_unit)
    return {"target_workflow_step": step, "target_section": section,
            "schedule": {"service_name": service_name, "interval_value": interval_value,
                         "interval_unit": interval_unit, "base_date": bd.isoformat(),
                         "base_date_source": base_date_source, "resolved_due_date": due.isoformat(),
                         "reason": reason, "sms_template": "appointment",
                         "prepare_reminders": prepare_reminders},
            "referral_prefill": None, "form_prefill": None, "required_fields": [], "missing_fields": []}


def referral_action(*, reason, urgency, department, requested_evaluation, note,
                    step="referral_navigation", section="Referral"):
    return {"target_workflow_step": step, "target_section": section, "schedule": None,
            "referral_prefill": {"referral_reason": reason, "referral_urgency": urgency,
                                 "referral_department": department,
                                 "requested_evaluation": requested_evaluation,
                                 "navigation_notes": note},
            "form_prefill": None, "required_fields": [], "missing_fields": []}


def required_form_action(*, step, section, required_fields=None, missing_fields=None, form_prefill=None):
    return {"target_workflow_step": step, "target_section": section, "schedule": None,
            "referral_prefill": None, "form_prefill": form_prefill or {},
            "required_fields": required_fields or [], "missing_fields": missing_fields or []}


def _hpv_test_date(facts):
    for k in ("hpv_sample_collection_date", "hpv_result_available_date", "latest_hpv_test_date"):
        if facts.get(k):
            return facts[k], k
    return None, None


# ---------------------------------------------------------------- HPV (section 6)
def map_hpv(facts: dict) -> dict:
    r = str(facts.get("hpv_result") or "").lower()
    hiv = str(facts.get("hiv_status") or "").lower()
    fu = {"hpv_result": r or None, "hiv_status": hiv or None}
    if r == "negative":
        if hiv in ("unknown", "not_disclosed", ""):
            return _rec("amber", "Confirm HIV status", "open_required_form",
                        "Confirm HIV status to calculate the correct HPV re-screening interval: 5 years if HIV negative and 3 years if HIV positive.",
                        facts_used=fu,
                        action_payload=required_form_action(step="register_client", section="Risk factors",
                                                            required_fields=["hiv_status"], missing_fields=["hiv_status"]))
        interval = 3 if hiv == "positive" else 5
        title = "Re-screen after %d years" % interval
        reason = ("HR-HPV negative. HIV-%s women should undergo HPV screening every %d years."
                  % ("positive" if hiv == "positive" else "negative", interval))
        bd, src = _hpv_test_date(facts)
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name=HPV_RESCREEN, interval_value=interval, interval_unit="years",
                                  base_date=bd, base_date_source=src or "hpv_sample_collection_date",
                                  reason="HR-HPV negative and HIV %s" % (hiv or "negative"))
        if payload is None:
            return _rec("amber", "Record the HPV test date", "open_required_form",
                        "Enter the HPV sample/result date to calculate the re-screening due date.",
                        facts_used=fu, action_payload=required_form_action(step="screening_test", section="HPV",
                        required_fields=["hpv_sample_collection_date"], missing_fields=["hpv_sample_collection_date"]))
        return _rec("green", title, "schedule_followup", reason, facts_used={**fu, "hpv_test_date": bd}, action_payload=payload)
    if r == "positive":
        return _rec("amber", "Triage HPV-positive client", "open_required_form",
                    "HPV positive — triage per selected pathway (VIA/colposcopy/genotyping).",
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="VIA"))
    if r == "invalid_or_unsatisfactory":
        return _rec("amber", "Repeat HPV sample", "schedule_followup",
                    "Invalid/unsatisfactory HPV — repeat sample or refer depending on context.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="HPV"))
    return _rec("silent", "No HPV decision", "no_action_required", "No HPV-based decision.", facts_used=fu)


# ---------------------------------------------------------------- VIA eligibility (section 7)
_VIA_ELIG_FIELDS = ["woman_very_ill", "pregnancy_status", "gestational_age_weeks", "postpartum_status",
                    "postpartum_weeks_since_delivery", "mass_suspicious_for_invasive_disease",
                    "history_treatment_precancer_or_cancer", "known_allergy_to_acetic_acid",
                    "history_total_hysterectomy"]


def map_via_eligibility(facts: dict) -> dict:
    """VIA eligibility pre-check; runs before VIA interpretation (section 7)."""
    fu = {k: facts.get(k) for k in _VIA_ELIG_FIELDS if facts.get(k) is not None}
    ill = normalize_yes_no_unknown(facts.get("woman_very_ill"))
    mass = normalize_yes_no_unknown(facts.get("mass_suspicious_for_invasive_disease"))
    preg = str(facts.get("pregnancy_status") or "").lower()
    ga = facts.get("gestational_age_weeks")
    pp = normalize_yes_no_unknown(facts.get("postpartum_status"))
    ppw = facts.get("postpartum_weeks_since_delivery")
    prior = normalize_yes_no_unknown(facts.get("history_treatment_precancer_or_cancer"))
    allergy = normalize_yes_no_unknown(facts.get("known_allergy_to_acetic_acid"))
    hyst = normalize_yes_no_unknown(facts.get("history_total_hysterectomy"))

    if mass == "yes":
        return _rec("red", "Do not perform VIA — refer for evaluation", "create_referral",
                    "Suspected invasive cervical disease — do not perform routine VIA or ablation. Refer for appropriate evaluation, biopsy and further management.",
                    facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent",
                    department="gynaecology", requested_evaluation=["evaluation", "biopsy", "further management"],
                    note="VIA findings/exam suspicious for invasive cervical disease. Refer for appropriate evaluation, biopsy and further management. Do not perform ablation."))
    if ill == "yes":
        return _rec("amber", "Defer VIA — address the acute condition", "open_required_form",
                    "VIA is excluded when the woman is very ill. Address the acute clinical condition first.",
                    facts_used=fu, action_payload=required_form_action(step="register_client", section="Relevant reproductive, medical & surgical history"))
    # P0.3: an explicit 'unknown' answer is missing information, not a satisfied exclusion.
    missing = [f for f in ("woman_very_ill", "pregnancy_status", "postpartum_status",
                           "mass_suspicious_for_invasive_disease", "history_treatment_precancer_or_cancer",
                           "known_allergy_to_acetic_acid", "history_total_hysterectomy")
               if _is_unknown(facts.get(f))]
    if preg == "pregnant" and _is_unknown(ga):
        missing.append("gestational_age_weeks")
    if pp == "yes" and _is_unknown(ppw):
        missing.append("postpartum_weeks_since_delivery")
    if hyst == "yes" and _is_unknown(facts.get("hysterectomy_indication")):
        missing.append("hysterectomy_indication")
    if missing:
        return _rec("amber", "Complete VIA eligibility check", "open_required_form",
                    "Required VIA eligibility information is incomplete or unknown. Complete the missing fields before VIA.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test",
                    section="VIA eligibility check", required_fields=_VIA_ELIG_FIELDS, missing_fields=missing))
    if preg == "pregnant" and isinstance(ga, (int, float)) and ga > 12:
        return _rec("amber", "Do not perform VIA in the 2nd/3rd trimester", "open_required_form",
                    "Do not perform VIA in the second or third trimester. Re-evaluate 6 weeks postpartum or use an appropriate method.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="Screening Method / Test"))
    if pp == "yes" and isinstance(ppw, (int, float)) and ppw < 6:
        dod = facts.get("date_of_delivery")
        if not dod:
            # §16: never invent an index date — require the delivery date to schedule
            return _rec("amber", "Record the delivery date", "open_required_form",
                        "Screening should resume 6 weeks postpartum. Enter the delivery date to calculate the resume date.",
                        facts_used=fu, action_payload=required_form_action(step="register_client",
                        section="Relevant reproductive, medical & surgical history",
                        required_fields=["date_of_delivery"], missing_fields=["date_of_delivery"]))
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Cervical cancer screening (resume postpartum)",
                                  interval_value=6, interval_unit="weeks", base_date=dod,
                                  base_date_source="date_of_delivery", reason="Resume screening at 6 weeks postpartum")
        return _rec("green", "Resume screening at 6 weeks after delivery", "schedule_followup",
                    "Cervical cancer screening should resume at 6 weeks postpartum.", facts_used=fu, action_payload=payload)
    if prior == "yes":
        return _rec("amber", "Use surveillance pathway, not routine VIA", "open_required_form",
                    "Prior cervical precancer/cancer treatment identified. Use the appropriate surveillance or specialist follow-up pathway rather than routine VIA screening.",
                    facts_used=fu, action_payload=required_form_action(step="followup_surveillance", section="Follow-up"))
    if allergy == "yes":
        return _rec("amber", "Do not use VIA — select another method", "open_required_form",
                    "Do not use VIA because of known acetic acid allergy. Select an alternative screening method such as HPV testing or cytology according to availability and pathway eligibility.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="Screening Method / Test", form_prefill={"highlight": ["HPV", "Cytology"]}))
    if hyst == "yes":
        return map_special_hysterectomy(facts)
    return _rec("silent", "VIA eligibility met", "no_action_required", "No VIA exclusion criteria present.", facts_used=fu)


# ---------------------------------------------------------------- VIA interpretation (section 8)
def map_via(facts: dict) -> dict:
    v = str(facts.get("via_result") or "").upper()
    hiv = str(facts.get("hiv_status") or "").lower()
    fu = {"via_result": v or None, "hiv_status": hiv or None}
    if v == "VIA_NEGATIVE":
        if hiv in ("unknown", "not_disclosed", ""):
            return _rec("amber", "Confirm HIV status to set VIA interval", "open_required_form",
                        "VIA-negative follow-up is 3 years for HIV-negative women and annual for HIV-infected women.",
                        facts_used=fu, action_payload=required_form_action(step="register_client", section="Risk factors",
                        required_fields=["hiv_status"], missing_fields=["hiv_status"]))
        if hiv == "positive":
            interval, unit, title, reason = 1, "years", "Re-screen annually", "VIA negative — re-screen annually because the woman is HIV infected."
        else:
            interval, unit, title, reason = 3, "years", "Re-screen every 3 years", "VIA negative — routine VIA re-screening is due in 3 years."
        bd = facts.get("via_exam_date")
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Routine cervical cancer rescreening — VIA",
                                  interval_value=interval, interval_unit=unit, base_date=bd,
                                  base_date_source="via_exam_date", reason=reason)
        if payload is None:
            return _rec("amber", "Record the VIA exam date", "open_required_form",
                        "Enter the VIA exam date to calculate the re-screening due date.", facts_used=fu,
                        action_payload=required_form_action(step="screening_test", section="VIA",
                        required_fields=["via_exam_date"], missing_fields=["via_exam_date"]))
        return _rec("green", title, "schedule_followup", reason, facts_used=fu, action_payload=payload)
    if v == "SUSPICIOUS_FOR_CANCER":
        return _rec("red", "Refer for appropriate evaluation, biopsy and further management", "create_referral",
                    "VIA findings are suspicious for invasive cervical disease. Do not perform ablation.",
                    facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent",
                    department="gynaecology", requested_evaluation=["appropriate evaluation", "biopsy", "further management"],
                    note="VIA findings are suspicious for invasive cervical disease. Refer for appropriate evaluation, biopsy and further management. Do not perform ablation."))
    if v == "VIA_POSITIVE":
        return _rec("amber", "Assess eligibility for ablative treatment", "open_required_form",
                    "VIA is positive. Complete the ablation eligibility assessment before selecting treatment.",
                    facts_used=fu, action_payload=required_form_action(step="treatment_eligibility", section="Ablation eligibility"))
    if v == "INADEQUATE_UNSATISFACTORY":
        return _rec("amber", "Repeat VIA or refer", "open_required_form",
                    "Inadequate/unsatisfactory VIA — repeat after treating cause, or refer.", facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="VIA"))
    return _rec("silent", "No VIA decision", "no_action_required", "No actionable VIA result.", facts_used=fu)


# ---------------------------------------------------------------- cytology (kept)
def map_cytology(facts: dict) -> dict:
    c = str(facts.get("cytology_result") or "").upper()
    t = str(facts.get("hr_hpv_triage_result") or "not_applicable").lower()
    fu = {"cytology_result": c or None, "hr_hpv_triage_result": t}
    negative, ascus = {"NILM"}, {"ASC_US"}
    gt_ascus = {"LSIL", "ASC_H", "HSIL", "AGC", "AIS", "SQUAMOUS_CELL_CARCINOMA", "ADENOCARCINOMA", "OTHER_MALIGNANT_NEOPLASM"}
    if c in negative:
        if _is_unknown(facts.get("cytology_sample_date")):
            return _missing_index_date_rec("cytology_sample_date", "screening_test", "Cytology", "cytology sample date")
        return _rec("green", "Rescreen in 3 years", "schedule_followup", "NILM — rescreen every 3 years.",
                    facts_used=fu, action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                    service_name="Routine cervical cancer rescreening — cytology", interval_value=3, interval_unit="years",
                    base_date=facts.get("cytology_sample_date"),
                    base_date_source="cytology_sample_date", reason="NILM"))
    if c in ascus:
        if t == "positive":
            return _rec("amber", "Colposcopy", "create_referral", "ASC-US with HPV positive — colposcopy.", facts_used=fu,
                        action_payload=referral_action(reason="colposcopy_needed", urgency="priority", department="colposcopy",
                        requested_evaluation=["colposcopy"], note="ASC-US with HR-HPV positive — refer for colposcopy."))
        if t == "negative":
            if _is_unknown(facts.get("cytology_sample_date")):
                return _missing_index_date_rec("cytology_sample_date", "screening_test", "Cytology", "cytology sample date")
            return _rec("green", "Rescreen in 3 years", "schedule_followup", "ASC-US with HPV negative — rescreen every 3 years.",
                        facts_used=fu, action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                        service_name="Routine cervical cancer rescreening — cytology", interval_value=3, interval_unit="years",
                        base_date=facts.get("cytology_sample_date"), base_date_source="cytology_sample_date", reason="ASC-US/HPV-"))
        return _rec("amber", "Do HR-HPV triage", "open_required_form", "ASC-US — perform high-risk HPV triage.", facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="Cytology", required_fields=["hr_hpv_triage_result"], missing_fields=["hr_hpv_triage_result"]))
    if c in gt_ascus:
        return _rec("amber", "Colposcopy", "create_referral", "%s — refer for colposcopy." % c, facts_used=fu,
                    action_payload=referral_action(reason="colposcopy_needed", urgency="priority", department="colposcopy",
                    requested_evaluation=["colposcopy"], note="Cytology %s — refer for colposcopy." % c))
    if c == "UNSATISFACTORY":
        return _rec("amber", "Repeat cytology or refer", "open_required_form", "Unsatisfactory cytology — repeat or refer.", facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="Cytology"))
    return _rec("silent", "No cytology decision", "no_action_required", "No cytology-based action.", facts_used=fu)


# ---------------------------------------------------------------- colposcopy (section 9)
def map_colposcopy(facts: dict) -> dict:
    r = str(facts.get("colposcopy_result") or "").upper()
    biopsy_kit = normalize_yes_no_unknown(facts.get("biopsy_kit_available"))
    biopsy_done = str(facts.get("biopsy_done") or "").lower()
    fu = {"colposcopy_result": r or None, "biopsy_kit_available": biopsy_kit, "biopsy_done": biopsy_done or None}
    if r == "COLPOSCOPY_NEGATIVE":
        bd = facts.get("colposcopy_date")
        if not _d(bd):
            return _rec("amber", "Record the colposcopy date", "open_required_form",
                        "Enter the colposcopy date to schedule the 12-month HPV surveillance test.", facts_used=fu,
                        action_payload=required_form_action(step="diagnostic_assessment", section="Colposcopy",
                        required_fields=["colposcopy_date"], missing_fields=["colposcopy_date"]))
        return _rec("green", "Re-test with HPV in 12 months", "schedule_followup",
                    "No lesion was identified on colposcopy. Re-test with HPV in 12 months. If HPV remains positive at 24 months, repeat colposcopy.",
                    facts_used=fu, action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                    service_name="HPV surveillance after negative colposcopy", interval_value=12, interval_unit="months",
                    base_date=bd, base_date_source="colposcopy_date", reason="Negative colposcopy — 12-month HPV surveillance"))
    if r == "SUSPICIOUS_FOR_CANCER":
        return _rec("red", "Refer for evaluation and diagnosis", "create_referral",
                    "Colposcopy suspicious for cancer — refer for evaluation and diagnosis.", facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent", department="gynaecology",
                    requested_evaluation=["evaluation", "biopsy", "further management"], note="Colposcopy suspicious for invasive cancer — refer."))
    if r == "COLPOSCOPY_POSITIVE":
        if biopsy_done == "yes" and facts.get("biopsy_result"):
            return map_histology(facts)
        if biopsy_kit == "unknown":
            return _rec("amber", "Confirm biopsy availability", "open_required_form",
                        "A positive colposcopy requires biopsy where biopsy is available. If biopsy is unavailable, assess eligibility for ablative treatment.",
                        facts_used=fu, action_payload=required_form_action(step="diagnostic_assessment", section="Colposcopy",
                        required_fields=["biopsy_kit_available"], missing_fields=["biopsy_kit_available"]))
        if biopsy_kit == "yes":
            return _rec("amber", "Perform a biopsy", "open_required_form",
                        "Colposcopy is positive and biopsy is available. Perform a biopsy and record the histology result.",
                        facts_used=fu, action_payload=required_form_action(step="diagnostic_assessment", section="Histology / biopsy",
                        form_prefill={"biopsy_done": "pending"}))
        return _rec("amber", "Assess eligibility for ablative treatment", "open_required_form",
                    "Colposcopy is positive and biopsy is unavailable. Complete the ablation eligibility assessment.",
                    facts_used=fu, action_payload=required_form_action(step="treatment_eligibility", section="Ablation eligibility"))
    if r == "INADEQUATE_COLPOSCOPY":
        return _rec("amber", "Repeat colposcopy or refer", "open_required_form", "Inadequate colposcopy — repeat or refer.", facts_used=fu,
                    action_payload=required_form_action(step="diagnostic_assessment", section="Colposcopy"))
    return _rec("silent", "No colposcopy decision", "no_action_required", "No colposcopy-based action.", facts_used=fu)


def map_colposcopy_negative_surveillance(facts: dict) -> dict:
    """Longitudinal: persistent HPV after a negative colposcopy (section 9.2)."""
    ncd = _d(facts.get("prior_negative_colposcopy_date"))
    hpv = str(facts.get("latest_hpv_result") or facts.get("hpv_result") or "").lower()
    if not ncd or hpv != "positive":
        return _rec("silent", "No surveillance decision", "no_action_required", "", facts_used={})
    mo = months_between(ncd, date.today())
    fu = {"prior_negative_colposcopy_date": ncd.isoformat(), "latest_hpv_result": hpv, "months_since_negative_colposcopy": mo}
    if mo >= 24:
        colpo_here = str(facts.get("facility_provides_colposcopy") or "").lower() == "yes"
        if colpo_here:
            return _rec("amber", "Repeat colposcopy", "open_required_form",
                        "HPV remains positive at 24 months after a negative colposcopy. Repeat colposcopy.", facts_used=fu,
                        action_payload=required_form_action(step="diagnostic_assessment", section="Colposcopy"))
        return _rec("amber", "Repeat colposcopy", "create_referral",
                    "HPV remains positive at 24 months after a negative colposcopy. Repeat colposcopy.", facts_used=fu,
                    action_payload=referral_action(reason="colposcopy_needed", urgency="priority", department="colposcopy",
                    requested_evaluation=["repeat colposcopy"], note="Persistent HPV positivity 24 months after negative colposcopy — repeat colposcopy."))
    if 9 <= mo <= 18:
        due = add_interval(ncd, 24, "months")
        return _rec("amber", "Repeat HPV surveillance; colposcopy at 24 months if still positive", "schedule_followup",
                    "HPV remains positive after a negative colposcopy. Repeat HPV surveillance. If HPV remains positive at 24 months from the negative colposcopy, repeat colposcopy.",
                    facts_used=fu, action_payload={"target_workflow_step": "followup_surveillance", "target_section": "Follow-up",
                    "schedule": {"service_name": "HPV surveillance after negative colposcopy", "interval_value": 24, "interval_unit": "months",
                                 "base_date": ncd.isoformat(), "base_date_source": "prior_negative_colposcopy_date",
                                 "resolved_due_date": due.isoformat(), "reason": "Persistent HPV — 24-month surveillance point",
                                 "sms_template": "appointment", "prepare_reminders": True},
                    "referral_prefill": None, "form_prefill": None, "required_fields": [], "missing_fields": []})
    return _rec("silent", "No surveillance decision", "no_action_required", "", facts_used=fu)


# ---------------------------------------------------------------- histology (kept)
_BIOPSY_GROUP = {"BENIGN_OR_NORMAL": "CIN1_OR_LESS", "CIN1": "CIN1_OR_LESS", "CIN2": "CIN2_PLUS", "CIN3": "CIN2_PLUS",
                 "AIS": "CIN2_PLUS_OR_GLANDULAR_HIGH_GRADE", "INVASIVE_CANCER": "CANCER",
                 "UNSATISFACTORY": "UNSATISFACTORY", "PENDING": "PENDING", "NOT_DONE": "NOT_DONE"}


def biopsy_group(biopsy_result: str) -> str:
    return _BIOPSY_GROUP.get((biopsy_result or "").upper(), "NOT_DONE")


def map_histology(facts: dict) -> dict:
    g = biopsy_group(facts.get("biopsy_result"))
    fu = {"biopsy_result": facts.get("biopsy_result"), "group": g}
    if g == "CIN1_OR_LESS":
        if _is_unknown(facts.get("biopsy_date")):
            return _missing_index_date_rec("biopsy_date", "diagnostic_assessment", "Histology / biopsy", "biopsy / histology date")
        return _rec("green", "Rescreen in 3 years", "schedule_followup", "CIN1 or less — rescreen within 3 years.", facts_used=fu,
                    action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                    service_name="Cervical cancer rescreening", interval_value=3, interval_unit="years",
                    base_date=facts.get("biopsy_date"), base_date_source="biopsy_date", reason="CIN1 or less"))
    if g == "CIN2_PLUS":
        return _rec("amber", "Treat with ablation or LEEP", "open_required_form", "CIN2/CIN3 — treat with ablation or LEEP.", facts_used=fu,
                    action_payload=required_form_action(step="treatment_eligibility", section="Ablation eligibility"))
    if g == "CIN2_PLUS_OR_GLANDULAR_HIGH_GRADE":
        return _rec("amber", "Specialist review / excision", "create_referral", "AIS — specialist review / excisional treatment.", facts_used=fu,
                    action_payload=referral_action(reason="treatment_needed", urgency="priority", department="gynaecology",
                    requested_evaluation=["specialist review", "excisional treatment"], note="AIS on histology — specialist review / excision."))
    if g == "CANCER":
        return _rec("red", "Refer for cancer staging", "create_referral", "Invasive cancer — refer for staging and treatment.", facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent", department="oncology",
                    requested_evaluation=["staging", "treatment"], note="Invasive cervical cancer on histology — refer for staging and treatment."))
    if g == "UNSATISFACTORY":
        return _rec("amber", "Repeat biopsy or refer", "open_required_form", "Unsatisfactory biopsy — repeat or refer.", facts_used=fu,
                    action_payload=required_form_action(step="diagnostic_assessment", section="Histology / biopsy"))
    return _rec("silent", "No histology decision", "no_action_required", "No histology-based action.", facts_used=fu)


# ---------------------------------------------------------------- ablation eligibility (section 10)
# Exactly the 10 canonical positive-eligibility criteria (audit §8). Each is yes|no|unknown.
_ABL_CRITERIA = [
    "ablation_c1_positive_screen_or_eligible_precancer",
    "ablation_c2_entire_lesion_and_margins_visible",
    "ablation_c3_lesion_lte_75_percent",
    "ablation_c4_no_canal_gt2mm_or_vaginal_extension",
    "ablation_c5_probe_full_coverage_no_gap_gt2mm",
    "ablation_c6_no_suspicion_invasive_cancer",
    "ablation_c7_no_active_pid_cervicitis_or_polyp",
    "ablation_c8_not_pregnant_and_postpartum_6w_or_more",
    "ablation_c9_no_prior_precancer_treatment",
    "ablation_c10_informed_consent_given",
]
_ABL_REQUIRED = list(_ABL_CRITERIA)  # kept name for callers
ABLATION_CHECKLIST_VERSION = "ablation-eligibility-v2"


def derive_ablation_eligibility(facts: dict) -> dict:
    """Derive eligibility purely from the 10 canonical checklist criteria (audit §8, review P0.2).
    Only ten explicit 'yes' answers can produce eligible. An explicit 'unknown' (or blank/absent)
    is missing information, never a satisfied criterion.
    Order: criterion 6 = no -> suspected cancer (red); any other no -> not_eligible;
    any unknown/missing -> unknown_missing_information; all-yes -> eligible."""
    vals = {i + 1: ("unknown" if _is_unknown(facts.get(cid)) else normalize_yes_no_unknown(facts.get(cid)))
            for i, cid in enumerate(_ABL_CRITERIA)}
    missing = [i for i, cid in enumerate(_ABL_CRITERIA, start=1) if _is_unknown(facts.get(cid))]
    failed = [i for i, v in vals.items() if v == "no"]
    result = {"failed_criteria": failed, "missing_criteria": missing,
              "derived_from_checklist_version": ABLATION_CHECKLIST_VERSION,
              "exclusion_reasons": [f"CRITERION_{i}_NOT_MET" for i in failed], "missing": [_ABL_CRITERIA[i - 1] for i in missing]}
    # criterion 6 (no suspicion of invasive cancer) answered "no" => suspected cancer pathway (red)
    if vals.get(6) == "no":
        result.update({"eligibility": "not_eligible", "suspected_cancer": True})
        return result
    if failed:
        result.update({"eligibility": "not_eligible", "suspected_cancer": False})
        return result
    if missing:
        result.update({"eligibility": "unknown_missing_information", "suspected_cancer": False})
        return result
    # eligible ONLY if every criterion is an explicit yes (never inferred from "no failed criteria")
    if all(v == "yes" for v in vals.values()):
        result.update({"eligibility": "eligible", "suspected_cancer": False})
        return result
    result.update({"eligibility": "unknown_missing_information", "suspected_cancer": False})
    return result


def map_eligibility(facts: dict) -> dict:
    d = derive_ablation_eligibility(facts)
    fu = {"derived_eligibility": d["eligibility"], "failed_criteria": d["failed_criteria"],
          "missing_criteria": d["missing_criteria"], "checklist_version": d["derived_from_checklist_version"]}
    if d.get("suspected_cancer"):
        return _rec("red", "Do not perform ablation — refer for evaluation", "create_referral",
                    "Criterion 6 indicates suspicion of invasive cancer. Do not perform ablation or routine precancer treatment. Refer for appropriate evaluation, biopsy and further management.",
                    facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent", department="gynaecology",
                    requested_evaluation=["evaluation", "biopsy", "further management"], note="Suspected invasive cancer on ablation checklist (criterion 6) — do not ablate; refer."))
    if d["eligibility"] == "unknown_missing_information":
        return _rec("amber", "Complete the ablation eligibility checklist", "open_required_form",
                    "Ablation eligibility cannot be determined because one or more checklist criteria are unanswered.",
                    facts_used=fu, action_payload=required_form_action(step="treatment_eligibility", section="Ablation eligibility",
                    required_fields=_ABL_CRITERIA, missing_fields=d["missing"]))
    if d["eligibility"] == "eligible":
        return _rec("green", "Eligible for ablative treatment", "open_required_form",
                    "All ten checklist criteria are met. The lesion is eligible for ablation.", facts_used=fu,
                    action_payload=required_form_action(step="precancer_treatment", section="Procedure",
                    form_prefill={"highlight": ["cryotherapy", "thermal_ablation"]}))
    return _rec("amber", "Not eligible for ablation — use excisional/referral pathway", "create_referral",
                f"Not eligible for ablative treatment. Criteria not met: {', '.join(str(i) for i in d['failed_criteria'])}. Use LEEP/excision or referral per facility capability.",
                facts_used=fu, action_payload=referral_action(reason="treatment_needed", urgency="priority", department="gynaecology",
                requested_evaluation=["LEEP", "excisional treatment"], note="Not eligible for ablation — refer for LEEP/excisional treatment."))


# ---------------------------------------------------------------- special populations (section 11)
def map_special_pregnancy(facts: dict) -> dict:
    if str(facts.get("pregnancy_status") or "").lower() != "pregnant":
        return _rec("silent", "", "no_action_required", "", facts_used={})
    ga = facts.get("gestational_age_weeks")
    fu = {"pregnancy_status": "pregnant", "gestational_age_weeks": ga}
    if str(facts.get("mass_suspicious_for_invasive_disease") or "").lower() == "yes":
        return _rec("red", "Refer for skilled evaluation and biopsy", "create_referral",
                    "Biopsy may be performed in any trimester by a skilled provider; heavy bleeding may occur.", facts_used=fu, blocking=True,
                    action_payload=referral_action(reason="suspected_cancer", urgency="urgent", department="gynaecology",
                    requested_evaluation=["skilled evaluation", "biopsy"],
                    note="Pregnant patient with a lesion suspicious for invasive cervical disease. Refer for skilled evaluation and biopsy. Biopsy may be undertaken in any trimester by an appropriately skilled provider; heavy bleeding may occur during the procedure."))
    if facts.get("precancer_treatment_indicated") in (True, "yes"):
        dod = facts.get("date_of_delivery")
        if dod:
            payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                      service_name="Re-evaluate precancer treatment postpartum", interval_value=6, interval_unit="weeks",
                                      base_date=dod, base_date_source="date_of_delivery", reason="Defer precancer treatment to 6 weeks postpartum")
            return _rec("amber", "Do not treat a precancerous lesion during pregnancy", "schedule_followup",
                        "Re-evaluate 6 weeks after delivery.", facts_used=fu, action_payload=payload, blocking=True)
        return _rec("amber", "Do not treat a precancerous lesion during pregnancy", "open_required_form",
                    "Do not perform treatment for a precancerous cervical lesion during pregnancy. Re-evaluate 6 weeks after delivery. Enter the expected delivery date to schedule re-evaluation.",
                    facts_used=fu, action_payload=required_form_action(step="followup_surveillance", section="Follow-up",
                    required_fields=["date_of_delivery"], missing_fields=["date_of_delivery"]), blocking=True)
    if isinstance(ga, (int, float)) and ga <= 12:
        return _rec("green", "First-trimester screening may proceed", "no_action_required",
                    "Screening can be performed in the first trimester up to the end of week 12.", facts_used=fu)
    if _is_unknown(ga):
        # §7: pregnancy-related missing information targets Register Client -> reproductive history,
        # NEVER Treatment Eligibility / Ablation checklist.
        return _rec("amber", "Record the gestational age", "open_required_form",
                    "Gestational age is needed to advise on screening during pregnancy.", facts_used=fu,
                    action_payload=required_form_action(step="register_client",
                    section="Relevant reproductive, medical & surgical history",
                    required_fields=["gestational_age_weeks"], missing_fields=["gestational_age_weeks"]))
    return _rec("silent", "", "no_action_required", "", facts_used=fu)


def map_special_postpartum(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("postpartum_status")) != "yes":
        return _rec("silent", "", "no_action_required", "", facts_used={})
    ppw = facts.get("postpartum_weeks_since_delivery")
    if isinstance(ppw, (int, float)) and ppw < 6:
        dod = facts.get("date_of_delivery")
        if not dod:
            return _rec("amber", "Record the delivery date", "open_required_form",
                        "Screening should resume 6 weeks postpartum. Enter the delivery date to calculate the resume date.",
                        facts_used={"postpartum_weeks_since_delivery": ppw},
                        action_payload=required_form_action(step="register_client",
                        section="Relevant reproductive, medical & surgical history",
                        required_fields=["date_of_delivery"], missing_fields=["date_of_delivery"]))
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Cervical cancer screening (resume postpartum)", interval_value=6, interval_unit="weeks",
                                  base_date=dod, base_date_source="date_of_delivery",
                                  reason="Resume screening at 6 weeks postpartum")
        return _rec("green", "Resume screening at 6 weeks after delivery", "schedule_followup",
                    "Cervical cancer screening should resume at 6 weeks postpartum.",
                    facts_used={"postpartum_weeks_since_delivery": ppw}, action_payload=payload)
    return _rec("silent", "", "no_action_required", "", facts_used={})


def map_special_hysterectomy(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("history_total_hysterectomy")) != "yes":
        return _rec("silent", "", "no_action_required", "", facts_used={})
    ind = str(facts.get("hysterectomy_indication") or "").lower()
    hg = normalize_yes_no_unknown(facts.get("history_high_grade_cin_or_cervical_cancer"))
    fu = {"history_total_hysterectomy": "yes", "hysterectomy_indication": ind or None, "history_high_grade_cin_or_cervical_cancer": hg}
    if not ind or ind == "unknown":
        return _rec("amber", "Confirm the reason for total hysterectomy", "open_required_form",
                    "The need for continued surveillance depends on whether the hysterectomy was performed for high-grade cervical precancer or cervical cancer.",
                    facts_used=fu, action_payload=required_form_action(step="register_client", section="Relevant reproductive, medical & surgical history",
                    required_fields=["hysterectomy_indication"], missing_fields=["hysterectomy_indication"]))
    if ind == "benign_or_non_cervical" and hg != "yes":
        return _rec("green", "Routine cervical screening is generally not required", "no_action_required",
                    "Total hysterectomy was not related to cervical cancer or severe precancer and no high-grade history is documented.", facts_used=fu)
    if ind in ("high_grade_cin_or_hsil", "cervical_cancer", "other_cervical_precancer") or hg == "yes":
        return _rec("amber", "Continue post-treatment surveillance", "open_required_form",
                    "Following hysterectomy for high-grade cervical precancer or cervical cancer, continued HPV testing or annual cytologic surveillance may be required to assess for vaginal disease or recurrence.",
                    facts_used=fu, action_payload=required_form_action(step="followup_surveillance", section="Follow-up",
                    required_fields=["post_hysterectomy_surveillance_method"]))
    return _rec("silent", "", "no_action_required", "", facts_used=fu)


def map_special_hpv_vaccinated(facts: dict) -> dict:
    v = str(facts.get("hpv_vaccination_status") or "").lower()
    if v not in ("vaccinated", "partially_vaccinated"):
        return _rec("silent", "", "no_action_required", "", facts_used={})
    return _rec("green", "Continue routine cervical cancer screening", "no_action_required",
                "HPV vaccination does not remove the need for routine screening.", facts_used={"hpv_vaccination_status": v})


def map_special_postmenopausal(facts: dict) -> dict:
    if str(facts.get("menopausal_status") or "").lower() != "postmenopausal":
        return _rec("silent", "", "no_action_required", "", facts_used={})
    age = facts.get("age_years") or facts.get("age")
    if isinstance(age, (int, float)) and age >= 65:
        return _rec("silent", "", "no_action_required", "", facts_used={})
    method = str(facts.get("screening_method") or facts.get("selected_screening_method") or "").lower()
    fu = {"menopausal_status": "postmenopausal", "age_years": age, "screening_method": method or None}
    if "cytolog" in method:
        idx = facts.get("cytology_sample_date") or facts.get("latest_test_date")
        if _is_unknown(idx):
            return _missing_index_date_rec("cytology_sample_date", "screening_test", "Cytology", "latest cytology test date")
        return _rec("green", "Cytology every 3 years until age 65", "schedule_followup",
                    "Continue cervical cancer screening using the postmenopausal interval.", facts_used=fu,
                    action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                    service_name="Routine cervical cancer rescreening — cytology", interval_value=3, interval_unit="years",
                    base_date=idx, base_date_source="cytology_sample_date", reason="Postmenopausal cytology interval"))
    if "hpv" in method:
        idx = facts.get("hpv_sample_collection_date") or facts.get("latest_hpv_test_date") or facts.get("latest_test_date")
        if _is_unknown(idx):
            return _missing_index_date_rec("hpv_sample_collection_date", "screening_test", "HPV", "latest HPV test date")
        return _rec("green", "HPV screening every 5 years until age 65", "schedule_followup",
                    "Continue cervical cancer screening using the postmenopausal interval.", facts_used=fu,
                    action_payload=schedule_action(step="followup_surveillance", section="Follow-up",
                    service_name=HPV_RESCREEN, interval_value=5, interval_unit="years",
                    base_date=idx, base_date_source="hpv_sample_collection_date", reason="Postmenopausal HPV interval"))
    return _rec("silent", "", "no_action_required", "", facts_used=fu)


def map_special_age65(facts: dict) -> dict:
    age = facts.get("age_years") or facts.get("age")
    if not (isinstance(age, (int, float)) and age >= 65):
        return _rec("silent", "", "no_action_required", "", facts_used={})
    hg = normalize_yes_no_unknown(facts.get("history_high_grade_cin_or_cervical_cancer"))
    nhpv = facts.get("negative_hpv_tests_last_10_years")
    npap = facts.get("negative_pap_tests_last_10_years")
    complete = facts.get("screening_history_complete_for_age65_exit_assessment")
    fu = {"age_years": age, "history_high_grade_cin_or_cervical_cancer": hg,
          "negative_hpv_tests_last_10_years": nhpv, "negative_pap_tests_last_10_years": npap}
    if hg == "yes":
        return _rec("amber", "Continue lifelong surveillance", "open_required_form",
                    "Surveillance should continue based on individual risk and prior disease history.", facts_used=fu,
                    action_payload=required_form_action(step="followup_surveillance", section="Follow-up"))
    adequate = (isinstance(nhpv, (int, float)) and nhpv >= 2) or (isinstance(npap, (int, float)) and npap >= 3)
    if adequate:
        return _rec("green", "Routine cervical cancer screening may stop", "no_action_required",
                    "Required negative screening history in the previous 10 years is documented and there is no high-grade lesion/cancer history.", facts_used=fu)
    if complete is False or (nhpv is None and npap is None):
        return _rec("amber", "Complete prior screening history before deciding whether routine screening can stop", "open_required_form",
                    "Enter historical screening tests to determine whether the >=65 screening-exit criteria are met.", facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="Other",
                    required_fields=["negative_hpv_tests_last_10_years", "negative_pap_tests_last_10_years"]))
    return _rec("silent", "", "no_action_required", "", facts_used=fu)


# ---------------------------------------------------------------- catalogue + evaluator
def validate_action_contract(action_code: str, action_payload: dict) -> list:
    """Return a list of contract violations for an action_code + action_payload pair (§14).
    Empty list means the payload is compatible with the action code."""
    pl = action_payload or {}
    errs = []
    if action_code == "schedule_followup":
        if not pl.get("schedule"):
            errs.append("schedule_followup requires action_payload.schedule")
        elif not pl["schedule"].get("resolved_due_date"):
            errs.append("schedule_followup requires a resolved_due_date")
        if pl.get("referral_prefill") and not pl.get("schedule"):
            errs.append("schedule_followup must not execute from a referral-only payload")
    elif action_code == "create_referral":
        ref = pl.get("referral_prefill") or {}
        if not ref.get("referral_reason"):
            errs.append("create_referral requires referral_prefill.referral_reason")
        if not ref.get("referral_urgency"):
            errs.append("create_referral requires referral_prefill.referral_urgency")
        if pl.get("schedule") and not pl.get("referral_prefill"):
            errs.append("create_referral must not execute from a schedule-only payload")
    elif action_code == "open_required_form":
        if not pl.get("target_workflow_step"):
            errs.append("open_required_form requires target_workflow_step")
        if not (pl.get("target_section") or pl.get("required_fields")):
            errs.append("open_required_form requires target_section and/or required_fields")
    return errs


def _missing_index_date_rec(date_field: str, step: str, section: str, label: str) -> dict:
    """Return an amber open_required_form recommendation when a clinical index date is missing.
    No executable schedule may be created from an invented date (review P0.5)."""
    return _rec("amber", f"Record the {label}", "open_required_form",
                f"A follow-up interval is indicated, but the {label} is missing. Enter it to calculate the due date.",
                facts_used={date_field: None},
                action_payload=required_form_action(step=step, section=section,
                required_fields=[date_field], missing_fields=[date_field]))


def catalog() -> dict:
    if _CATALOG_PATH.exists():
        return json.loads(_CATALOG_PATH.read_text())
    return {"rules": []}
    if _CATALOG_PATH.exists():
        return json.loads(_CATALOG_PATH.read_text())
    return {"rules": []}


_DISPATCH = {
    "cc.hpv.interpretation": (map_hpv, "hpv_result"),
    "cc.via.eligibility": (map_via_eligibility, "via_exam_date"),
    "cc.via.interpretation": (map_via, "via_result"),
    "cc.cytology.interpretation": (map_cytology, "cytology_result"),
    "cc.colposcopy.interpretation": (map_colposcopy, "colposcopy_result"),
    "cc.colposcopy.negative_surveillance": (map_colposcopy_negative_surveillance, "prior_negative_colposcopy_date"),
    "cc.hpv.persistent_after_negative_colposcopy": (map_colposcopy_negative_surveillance, "prior_negative_colposcopy_date"),
    "cc.histology.interpretation": (map_histology, "biopsy_result"),
    "cc.eligibility.exclusions": (map_eligibility, "ablative_therapy_eligibility"),
    "cc.special.pregnancy": (map_special_pregnancy, "pregnancy_status"),
    "cc.special.postpartum": (map_special_postpartum, "postpartum_status"),
    "cc.special.total_hysterectomy": (map_special_hysterectomy, "history_total_hysterectomy"),
    "cc.special.hpv_vaccinated": (map_special_hpv_vaccinated, "hpv_vaccination_status"),
    "cc.special.postmenopausal": (map_special_postmenopausal, "menopausal_status"),
    "cc.special.age_65_plus": (map_special_age65, "age_years"),
}


def evaluate(facts: dict, *, only_enabled=True) -> list:
    """Evaluate the curated catalogue against workflow facts. Disabled rules never fire."""
    out = []
    cat = catalog()
    facts = dict(facts)
    if any(facts.get(c) is not None for c in _ABL_CRITERIA) or facts.get("via_result") == "VIA_POSITIVE" or facts.get("colposcopy_result") == "COLPOSCOPY_POSITIVE":
        facts.setdefault("ablative_therapy_eligibility", "assess")
    for rule in cat.get("rules", []):
        if only_enabled and rule.get("status") not in (None, "active"):
            continue
        fn_dep = _DISPATCH.get(rule["rule_id"])
        if not fn_dep:
            continue
        fn, primary = fn_dep
        # §7: a rule is ACTIVATED by its primary (trigger) input only. Dependent inputs refine an
        # already-active rule but must never activate it — otherwise entering an unrelated field
        # (e.g. pregnancy_status) raises an ablation-checklist recommendation and drags the
        # clinician toward Treatment Eligibility.
        if primary and _is_unknown(facts.get(primary)):
            continue
        rec = fn(facts)
        if rec["severity_class"] == "silent":
            continue
        rec.update({"rule_id": rule["rule_id"], "workflow_step": rule.get("workflow_step"),
                    "subsection": rule.get("subsection"), "guideline_page_refs": rule.get("guideline_refs", [])})
        out.append(rec)
    return out


# ---------------------------------------------------------------- follow-up calculator (kept API)
def followup_due_date(*, procedure_date=None, index_treatment_reason=None, referral_date=None,
                      referral_reason=None, referral_urgency=None, post_treatment_test_result=None,
                      followup_completed_date=None) -> dict:
    def out(due, basis, sf):
        return {"followup_due_date": due.isoformat() if due else None, "calculation_basis": basis,
                "source_fields": sf, "manual_override_allowed": True, "manual_override_requires_reason": True}
    if post_treatment_test_result:
        r = post_treatment_test_result.lower()
        base = _d(followup_completed_date)
        if r == "suspected_cancer":
            # urgent — measured from today's clinical review is acceptable as an overdue/urgent trigger
            return out(add_interval(base or date.today(), 7, "days"), "suspected cancer -> urgent evaluation/referral", ["post_treatment_test_result"])
        if base is None:
            # P0.5: do not invent an index date for a routine surveillance interval
            return {"followup_due_date": None, "calculation_basis": "post-treatment follow-up requires followup_completed_date",
                    "source_fields": ["followup_completed_date", "post_treatment_test_result"],
                    "missing_fields": ["followup_completed_date"], "manual_override_allowed": True, "manual_override_requires_reason": True}
        if r == "negative":
            return out(add_interval(base, 12, "months"), "post-treatment test negative -> repeat in 12 months", ["followup_completed_date", "post_treatment_test_result"])
        if r == "positive":
            return out(add_interval(base, 12, "months"), "post-treatment positive -> LEEP/cone then 12-month follow-up", ["followup_completed_date", "post_treatment_test_result"])
    if procedure_date:
        base = _d(procedure_date)
        if base:
            return out(add_interval(base, 12, "months"), "procedure_date + 12 months (index_treatment_reason=%s)" % (index_treatment_reason or "treated"), ["procedure_date", "index_treatment_reason"])
    if referral_date:
        base = _d(referral_date)
        if base:
            days = {"emergency": 3, "urgent": 7, "priority": 21, "routine": 30}.get((referral_urgency or "routine").lower(), 30)
            return out(add_interval(base, days, "days"), "referral follow-up in %d days" % days, ["referral_date", "referral_urgency"])
    return out(None, "insufficient inputs to calculate a follow-up date", [])


# =====================================================================================
# BREAST CANCER — v0.8.0
# Kenya National Cancer Screening & Early Diagnosis Guidelines, 2nd Ed., 2024 (breast).
# Deterministic clinical authority. See data/curated_cds/breast_guideline_conflicts.md
# for the policy decisions taken where the source text is internally inconsistent.
# LLMs never alter any outcome below.
# =====================================================================================

_BREAST_HIGH_RISK_FIELDS = [
    ("breast_first_degree_relative_affected", "FIRST_DEGREE_RELATIVE"),
    ("breast_previous_abnormal_biopsy", "PREVIOUS_ABNORMAL_BIOPSY"),
    ("breast_previous_chest_wall_radiation", "PREVIOUS_CHEST_WALL_RADIATION"),
    ("breast_previous_cancer", "PREVIOUS_BREAST_CANCER"),
    ("breast_known_pathogenic_mutation", "KNOWN_PATHOGENIC_MUTATION"),
]

_BREAST_SYMPTOM_FIELDS = ["breast_cbe_lump", "breast_cbe_pain", "breast_cbe_nipple_discharge",
                          "breast_cbe_skin_changes", "breast_cbe_axillary_nodes"]


def _num(v):
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _age_from_facts(facts: dict):
    """Age in whole years — prefer date_of_birth, else the age_years field."""
    dob = _d(facts.get("date_of_birth") or facts.get("birth_date"))
    if dob:
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    n = _num(facts.get("age_years") or facts.get("age"))
    return int(n) if n is not None else None


def _due_date_from_start_age(facts: dict, start_age: int):
    """First due date at a target start age, computed from date of birth (never from today)."""
    dob = _d(facts.get("date_of_birth") or facts.get("birth_date"))
    if not dob or start_age is None:
        return None
    return date(dob.year + int(start_age), dob.month, min(dob.day, 28))


# ---------------------------------------------------------------- derived breast facts
def derive_breast_symptomatic(facts: dict) -> dict:
    """True when CBE is abnormal or any concerning breast finding is explicitly present."""
    reasons = []
    if str(facts.get("breast_cbe_result") or "").lower() == "abnormal":
        reasons.append("abnormal_cbe")
    for f in _BREAST_SYMPTOM_FIELDS:
        if normalize_yes_no_unknown(facts.get(f)) == "yes":
            reasons.append(f)
    if normalize_yes_no_unknown(facts.get("breast_symptomatic_or_abnormal")) == "yes":
        reasons.append("breast_symptomatic_or_abnormal")
    return {"symptomatic": bool(reasons), "reasons": sorted(set(reasons))}


def derive_breast_triple_negative_current(facts: dict) -> dict:
    """Triple negative ONLY when ER, PR and HER2 are each explicitly negative (§6.5)."""
    er = str(facts.get("breast_er_status") or "").lower()
    pr = str(facts.get("breast_pr_status") or "").lower()
    her2 = str(facts.get("breast_her2_status") or "").lower()
    all_neg = er == "negative" and pr == "negative" and her2 == "negative"
    return {"triple_negative": bool(all_neg),
            "receptors": {"er": er or None, "pr": pr or None, "her2": her2 or None}}


def derive_breast_high_risk(facts: dict) -> dict:
    """§7.1 five-characteristic high-risk classifier. 'unknown' is never treated as 'no'."""
    reasons, missing = [], []
    for field, code in _BREAST_HIGH_RISK_FIELDS:
        v = normalize_yes_no_unknown(facts.get(field))
        if v == "yes":
            reasons.append(code)
        elif v == "unknown":
            missing.append(field)
    symptomatic = derive_breast_symptomatic(facts)["symptomatic"]
    genetics = derive_breast_genetics_referral(facts)["eligible"]
    if reasons:
        classification = "high_risk"
    elif not missing:
        classification = "average_risk"
    else:
        classification = "unknown_missing_information"
    return {"classification": classification, "high_risk_reasons": reasons,
            "missing_fields": missing, "symptomatic": symptomatic,
            "genetics_referral_eligible": genetics}


def derive_breast_genetics_referral(facts: dict) -> dict:
    """§10 genetic-counselling referral criteria. Any single criterion qualifies.
    Requires explicit values — unknown/missing never satisfies a criterion (§18)."""
    met = []
    ynu = normalize_yes_no_unknown
    cases = _num(facts.get("breast_family_breast_ovarian_cases_count"))
    gens = _num(facts.get("breast_family_generations_affected_count"))
    if (cases is not None and cases >= 3 and gens is not None and gens >= 2
            and ynu(facts.get("breast_family_any_onset_under_50")) == "yes"):
        met.append("THREE_PLUS_CASES_TWO_GENERATIONS_ONE_UNDER_50")
    if ynu(facts.get("breast_bilateral_primary_cancer")) == "yes":
        met.append("BILATERAL_PRIMARY_BREAST_CANCER")
    dx_age = _num(facts.get("breast_previous_cancer_diagnosis_age"))
    had_cancer = ynu(facts.get("breast_previous_cancer")) == "yes"
    if had_cancer and dx_age is not None and dx_age <= 35:
        met.append("BREAST_CANCER_AGE_35_OR_YOUNGER")
    tnbc = (ynu(facts.get("breast_triple_negative_cancer")) == "yes"
            or derive_breast_triple_negative_current(facts)["triple_negative"])
    if tnbc and dx_age is not None and dx_age <= 60:
        met.append("TRIPLE_NEGATIVE_AGE_60_OR_YOUNGER")
    if had_cancer and ynu(facts.get("breast_primary_ovarian_cancer_history")) == "yes":
        met.append("BREAST_AND_OVARIAN_SAME_INDIVIDUAL")
    if ynu(facts.get("breast_family_male_breast_cancer")) == "yes":
        male_age = _num(facts.get("breast_family_male_case_age"))
        close = ynu(facts.get("breast_family_male_case_close_family_history")) == "yes"
        if (male_age is not None and male_age <= 65) or close:
            met.append("MALE_BREAST_CANCER")
    if ynu(facts.get("breast_confirmed_brca1_brca2_in_family")) == "yes":
        met.append("CONFIRMED_BRCA_IN_FAMILY")
    return {"eligible": bool(met), "criteria_met": met, "missing_fields": []}


def calculate_family_history_mammography_start_age(facts: dict) -> dict:
    """§9.1: start = clamp(youngest_case_age - 10, 25, 40). Missing age -> request it."""
    youngest = _num(facts.get("breast_youngest_family_case_age"))
    if youngest is None:
        return {"start_age": None, "missing_fields": ["breast_youngest_family_case_age"]}
    start = min(40, max(25, int(youngest) - 10))
    return {"start_age": start, "missing_fields": []}


def calculate_radiation_mammography_start_age(facts: dict) -> dict:
    """§9.3: start = clamp(age_at_radiation + 5, 25, 40). Prefer explicit age; else derive
    from radiation date + date of birth. Missing both -> request information."""
    age_rad = _num(facts.get("breast_age_at_chest_wall_radiation"))
    if age_rad is None:
        rad_date = _d(facts.get("breast_chest_wall_radiation_date"))
        dob = _d(facts.get("date_of_birth") or facts.get("birth_date"))
        if rad_date and dob:
            age_rad = rad_date.year - dob.year - ((rad_date.month, rad_date.day) < (dob.month, dob.day))
    if age_rad is None:
        return {"start_age": None, "age_at_radiation": None,
                "missing_fields": ["breast_age_at_chest_wall_radiation", "breast_chest_wall_radiation_date"]}
    start = min(40, max(25, int(age_rad) + 5))
    return {"start_age": start, "age_at_radiation": int(age_rad), "missing_fields": []}


_BREAST_AGE_BANDS = [
    (0, 24, None, None, None, "Breast awareness and clinical review", "awareness"),
    (25, 34, ["CBE"], 3, "years", "Breast screening due: CBE", "cbe_3y"),
    (35, 39, ["CBE", "ultrasound"], 2, "years", "Breast screening due: CBE and ultrasound", "cbe_us_2y"),
    (40, 55, ["CBE", "mammography"], 1, "years", "Breast screening due: CBE and mammography", "cbe_mammo_1y"),
    (56, 74, ["CBE", "mammography"], 2, "years", "Breast screening due: CBE and mammography", "cbe_mammo_2y"),
    (75, 200, None, None, None, "Discuss whether to continue breast screening", "shared_decision"),
]


def _breast_age_band(age):
    if age is None:
        return None
    for lo, hi, modalities, iv, unit, title, key in _BREAST_AGE_BANDS:
        if lo <= age <= hi:
            return {"lo": lo, "hi": hi, "modalities": modalities, "interval_value": iv,
                    "interval_unit": unit, "title": title, "key": key}
    return None


def derive_breast_average_risk_eligibility(facts: dict) -> dict:
    """§7.2/§8: is the woman on the routine average-risk pathway, and if so which age band?"""
    hr = derive_breast_high_risk(facts)
    reasons_blocked = []
    if hr["symptomatic"]:
        reasons_blocked.append("symptomatic_or_abnormal_cbe")
    if normalize_yes_no_unknown(facts.get("breast_previous_cancer")) == "yes" \
            or normalize_yes_no_unknown(facts.get("breast_dcis_history")) == "yes":
        reasons_blocked.append("previous_breast_cancer_or_dcis")
    sex = str(facts.get("sex_at_registration") or facts.get("gender") or "").lower()
    if sex and sex not in ("female", "f"):
        reasons_blocked.append("not_female_routine_pathway")
    if hr["classification"] == "high_risk":
        reasons_blocked.append("high_risk_classification")
    if hr["classification"] == "unknown_missing_information":
        reasons_blocked.append("risk_classification_incomplete")
    eligible = not reasons_blocked
    band = _breast_age_band(_age_from_facts(facts)) if eligible else None
    return {"eligible": eligible, "blocked_reasons": reasons_blocked,
            "classification": hr["classification"], "missing_fields": hr["missing_fields"],
            "age_band": band, "age": _age_from_facts(facts)}


# ---------------------------------------------------------------- breast catalogue map fns
def _breast_engaged(facts: dict) -> bool:
    """A breast rule stays silent unless the breast pathway is actually engaged, so cervical-only
    encounters never see breast cards (avoids nuisance alerts; §14 trigger discipline)."""
    keys = [f for f, _ in _BREAST_HIGH_RISK_FIELDS] + _BREAST_SYMPTOM_FIELDS + [
        "breast_family_history_present", "breast_cbe_result", "breast_cbe_date",
        "breast_ultrasound_result", "mammography_birads", "mammography_date",
        "breast_histopathology_result", "breast_known_pathogenic_mutation",
        "breast_youngest_family_case_age", "breast_previous_biopsy_finding",
        "breast_screening_shared_decision"]
    return any(not _is_unknown(facts.get(k)) for k in keys)


def _breast_refs(*pages):
    return list(pages) or ["kenya_ncsedg_2024_breast"]


def map_bc_risk_classification(facts: dict) -> dict:
    if not _breast_engaged(facts):
        return _rec("silent", "No breast risk decision", "no_action_required", "", facts_used={})
    hr = derive_breast_high_risk(facts)
    fu = {"breast_high_risk_reasons": hr["high_risk_reasons"], "classification": hr["classification"],
          "symptomatic": hr["symptomatic"]}
    if hr["classification"] == "high_risk":
        return _rec("amber", "Breast risk: HIGH RISK", "open_required_form",
                    "High-risk breast-cancer characteristic present (%s). Use the high-risk screening "
                    "pathway; do not apply the average-risk schedule." % ", ".join(hr["high_risk_reasons"]),
                    facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="Breast screening plan"))
    if hr["classification"] == "unknown_missing_information":
        return _rec("amber", "Complete breast risk assessment", "open_required_form",
                    "Breast risk cannot be classified because required high-risk fields are unknown. "
                    "Complete them before an average-risk schedule can be offered — unknown is not 'no'.",
                    facts_used=fu,
                    action_payload=required_form_action(step="register_client",
                    section="Breast cancer risk assessment and history",
                    required_fields=hr["missing_fields"], missing_fields=hr["missing_fields"]))
    return _rec("green", "Breast risk: average risk", "no_action_required",
                "No defined high-risk characteristic. Apply the average-risk age/interval schedule.",
                facts_used=fu)


def map_bc_screening_average_risk(facts: dict) -> dict:
    if not _breast_engaged(facts):
        return _rec("silent", "No breast screening decision", "no_action_required", "", facts_used={})
    elig = derive_breast_average_risk_eligibility(facts)
    if not elig["eligible"]:
        # symptomatic/high-risk/incomplete are handled by their own rules; stay silent here (§19)
        return _rec("silent", "Average-risk screening not applicable", "no_action_required", "",
                    facts_used={"blocked_reasons": elig["blocked_reasons"]})
    band = elig["age_band"]
    age = elig["age"]
    fu = {"age": age, "classification": "average_risk",
          "age_band": band["key"] if band else None}
    if band is None:
        return _rec("amber", "Record age or date of birth", "open_required_form",
                    "Enter the date of birth (or age) to determine the average-risk breast screening band.",
                    facts_used=fu, action_payload=required_form_action(step="register_client",
                    section="Demographics", required_fields=["date_of_birth"], missing_fields=["date_of_birth"]))
    if band["key"] == "awareness":
        return _rec("green", "Breast awareness (under 25)", "no_action_required",
                    "Average risk and under 25: promote breast awareness and clinical review. "
                    "No age-based routine screening interval applies (Table 9).", facts_used=fu)
    if band["key"] == "shared_decision":
        decision = str(facts.get("breast_screening_shared_decision") or "").lower()
        if decision not in ("continue", "stop", "defer"):
            return _rec("amber", "Discuss whether to continue breast screening", "open_required_form",
                        "Age 75+: document a shared decision (continue / stop / defer) before scheduling.",
                        facts_used=fu, action_payload=required_form_action(step="screening_test",
                        section="Breast screening plan", required_fields=["breast_screening_shared_decision"],
                        missing_fields=["breast_screening_shared_decision"]))
        if decision != "continue":
            return _rec("green", "Breast screening: %s (shared decision)" % decision, "no_action_required",
                        "Shared decision recorded as '%s'. No automatic interval applied." % decision, facts_used=fu)
        band = {**band, "modalities": ["CBE", "mammography"], "interval_value": 2, "interval_unit": "years"}
    modalities = ", ".join(band["modalities"])
    # choose the base date from the most relevant prior test for this band
    base_field = "last_mammography_date" if "mammography" in band["modalities"] else "last_breast_cbe_date"
    base = facts.get(base_field) or facts.get("last_breast_cbe_date") or facts.get("last_breast_ultrasound_date")
    reason = ("Average risk, age %s (band %d-%d): %s every %d %s. Source date: %s." %
              (age, band["lo"], band["hi"], modalities, band["interval_value"], band["interval_unit"],
               base or "none on record"))
    if not base:
        return _rec("amber", band["title"] + " — due now", "open_required_form",
                    reason + " No previous relevant screening date on record, so screening is due now; "
                    "no historical base date is invented.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test",
                    section="Breast CBE"))
    payload = schedule_action(step="followup_surveillance", section="Follow-up",
                              service_name="Routine breast screening — %s" % modalities,
                              interval_value=band["interval_value"], interval_unit=band["interval_unit"],
                              base_date=base, base_date_source=base_field,
                              reason="Average-risk breast screening, band %d-%d" % (band["lo"], band["hi"]))
    if payload is None:
        return _rec("amber", band["title"] + " — due now", "open_required_form", reason,
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="Breast CBE"))
    return _rec("green", band["title"], "schedule_followup", reason, facts_used={**fu, "base_date": base},
                action_payload=payload)


def _breast_cbe_start(facts, age, start_age, modalities_title, base_field, mammo_start):
    """Shared high-risk builder: annual CBE from age 21, annual mammography from mammography start age."""
    fu = {"age": age, "mammography_start_age": mammo_start}
    if age is None:
        return _rec("amber", "Record age or date of birth", "open_required_form",
                    "Enter the date of birth (or age) to schedule high-risk breast screening.",
                    facts_used=fu, action_payload=required_form_action(step="register_client",
                    section="Demographics", required_fields=["date_of_birth"], missing_fields=["date_of_birth"]))
    return None  # caller continues


def map_bc_screening_high_risk_family_history(facts: dict) -> dict:
    if derive_breast_high_risk(facts)["classification"] != "high_risk":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    if normalize_yes_no_unknown(facts.get("breast_first_degree_relative_affected")) != "yes":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    n = _num(facts.get("breast_first_degree_relatives_count"))
    # applies to ONE or TWO first-degree relatives who do NOT meet genetics criteria (§9.1)
    if n is not None and n > 2:
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    if derive_breast_genetics_referral(facts)["eligible"]:
        return _rec("silent", "n/a — meets genetics criteria", "no_action_required", "", facts_used={})
    calc = calculate_family_history_mammography_start_age(facts)
    age = _age_from_facts(facts)
    fu = {"first_degree_relatives_count": n, "mammography_start_age": calc["start_age"], "age": age}
    if calc["start_age"] is None:
        return _rec("amber", "Record youngest family breast-cancer age", "open_required_form",
                    "High risk from family history. Enter the age of the youngest affected family case to "
                    "calculate the mammography start age (10 years younger, clamped to 25-40). No schedule is guessed.",
                    facts_used=fu, action_payload=required_form_action(step="register_client",
                    section="Breast cancer risk assessment and history",
                    required_fields=["breast_youngest_family_case_age"],
                    missing_fields=["breast_youngest_family_case_age"]),
                    )
    start = calc["start_age"]
    if age is None:
        return _rec("amber", "Record age or date of birth", "open_required_form",
                    "Enter the date of birth (or age) to schedule high-risk breast screening. "
                    "Mammography start age is %d." % start, facts_used=fu,
                    action_payload=required_form_action(step="register_client", section="Demographics",
                    required_fields=["date_of_birth"], missing_fields=["date_of_birth"]))
    # mammography schedule
    if age >= start:
        base = facts.get("last_mammography_date")
        if base:
            payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                      service_name="High-risk annual mammography (family history)",
                                      interval_value=1, interval_unit="years", base_date=base,
                                      base_date_source="last_mammography_date",
                                      reason="High-risk family history; annual mammography")
            title = "High-risk breast screening: annual CBE + mammography"
        else:
            return _rec("amber", "High-risk breast screening due now: CBE + mammography", "open_required_form",
                        "High risk (1-2 first-degree relatives). CBE annually from age 21 and annual mammography "
                        "(start age %d, reached). Complementary ultrasound/MRI only if clinically justified. "
                        "No mammogram date on record — screening is due now." % start,
                        facts_used=fu, action_payload=required_form_action(step="screening_test", section="Mammography"))
        return _rec("amber", title, "schedule_followup",
                    "High risk (1-2 first-degree relatives, not meeting genetics criteria). CBE annually from age 21; "
                    "annual mammography from age %d (reached). Complementary US/MRI only if clinically justified." % start,
                    facts_used={**fu, "base_date": base}, action_payload=payload)
    # below start age: CBE now if >=21, mammography future-dated from DOB
    due = _due_date_from_start_age(facts, start)
    msg = ("High risk (1-2 first-degree relatives). Annual CBE %s; annual mammography begins at age %d%s." %
           ("from age 21 (start now)" if age >= 21 else "eligible from age 21 (not yet)", start,
            (" (first mammogram ~%s)" % due.isoformat()) if due else ""))
    return _rec("amber", "High-risk breast screening plan (family history)", "open_required_form", msg,
                facts_used={**fu, "first_mammogram_due": due.isoformat() if due else None},
                action_payload=required_form_action(step="screening_test", section="Breast CBE"))


def map_bc_screening_high_risk_abnormal_biopsy(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("breast_previous_abnormal_biopsy")) != "yes":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    finding = str(facts.get("breast_previous_biopsy_finding") or "").lower()
    if finding not in ("atypical_hyperplasia", "lobular_carcinoma_in_situ"):
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    ruled_out = normalize_yes_no_unknown(facts.get("breast_invasive_carcinoma_ruled_out_after_biopsy"))
    fu = {"breast_previous_biopsy_finding": finding, "invasive_ruled_out": ruled_out}
    if ruled_out != "yes":
        return _rec("amber", "Breast biopsy: complete surgical review first", "create_referral",
                    "Atypical hyperplasia/LCIS but invasive carcinoma is not confirmed as ruled out. "
                    "This is not yet a screening pathway — route to diagnostic/surgical review.",
                    facts_used=fu, action_payload=referral_action(reason="breast_pathology_review",
                    urgency="priority", department="breast_surgery",
                    requested_evaluation=["surgical review", "exclude invasive carcinoma", "define management"],
                    note="Atypical hyperplasia/LCIS pending confirmation that invasive carcinoma is ruled out."))
    interval = _num(facts.get("breast_high_risk_cbe_interval_months"))
    base = facts.get("last_mammography_date") or facts.get("breast_previous_biopsy_date")
    if interval not in (6, 12):
        return _rec("amber", "Select CBE interval (6 or 12 months)", "open_required_form",
                    "High risk (atypical hyperplasia/LCIS, invasive carcinoma ruled out): CBE every 6-12 months and "
                    "annual mammography. Choose 6 or 12 months before the CBE appointment is created.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test",
                    section="Breast screening plan", required_fields=["breast_high_risk_cbe_interval_months"],
                    missing_fields=["breast_high_risk_cbe_interval_months"]))
    if base:
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="High-risk annual mammography (atypical hyperplasia/LCIS)",
                                  interval_value=1, interval_unit="years", base_date=base,
                                  base_date_source="last_mammography_date",
                                  reason="High-risk breast screening (abnormal biopsy)")
        return _rec("amber", "High-risk breast screening: CBE %d-monthly + annual mammography" % int(interval),
                    "schedule_followup",
                    "Atypical hyperplasia/LCIS with invasive carcinoma ruled out: CBE every %d months and annual "
                    "mammography from the last mammography/biopsy-management date." % int(interval),
                    facts_used={**fu, "cbe_interval_months": int(interval), "base_date": base},
                    action_payload=payload)
    return _rec("amber", "High-risk breast screening due now", "open_required_form",
                "Atypical hyperplasia/LCIS: CBE every %d months and annual mammography. No mammography/biopsy date "
                "on record — screening is due now." % int(interval),
                facts_used=fu, action_payload=required_form_action(step="screening_test", section="Mammography"))


def map_bc_screening_high_risk_chest_radiation(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("breast_previous_chest_wall_radiation")) != "yes":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    calc = calculate_radiation_mammography_start_age(facts)
    age_rad = calc["age_at_radiation"]
    fu = {"age_at_radiation": age_rad, "imaging_start_age": calc["start_age"]}
    if age_rad is None:
        return _rec("amber", "Record chest-wall radiation age/date", "open_required_form",
                    "High risk from chest-wall radiation. Enter the age at (or date of) radiation to calculate the "
                    "imaging start age. No schedule is guessed.", facts_used=fu,
                    action_payload=required_form_action(step="register_client",
                    section="Breast cancer risk assessment and history",
                    required_fields=["breast_age_at_chest_wall_radiation"],
                    missing_fields=["breast_age_at_chest_wall_radiation"]))
    if age_rad > 30:
        # the age<=30 high-risk imaging rule does not apply (§9.3); classified high-risk but no auto schedule here
        return _rec("green", "Chest-wall radiation after age 30", "no_action_required",
                    "Chest-wall radiation occurred after age 30, so the specific '<=30' annual mammography+MRI rule "
                    "does not apply. Manage per age/other risk factors and specialist advice.", facts_used=fu)
    start = calc["start_age"]
    age = _age_from_facts(facts)
    if age is not None and age >= start:
        base = facts.get("last_mammography_date")
        if base:
            payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                      service_name="High-risk annual mammography + MRI (chest radiation)",
                                      interval_value=1, interval_unit="years", base_date=base,
                                      base_date_source="last_mammography_date",
                                      reason="High-risk chest-wall radiation")
            return _rec("amber", "High-risk breast screening: annual CBE + mammography + MRI", "schedule_followup",
                        "Chest-wall radiation at age %d. Annual CBE; annual mammography and MRI from age %d (reached)." %
                        (age_rad, start), facts_used={**fu, "base_date": base}, action_payload=payload)
        return _rec("amber", "High-risk breast screening due now: CBE + mammography + MRI", "open_required_form",
                    "Chest-wall radiation at age %d. Annual CBE and annual mammography+MRI from age %d (reached). "
                    "No mammogram date on record — due now." % (age_rad, start),
                    facts_used=fu, action_payload=required_form_action(step="screening_test", section="Mammography"))
    due = _due_date_from_start_age(facts, start)
    return _rec("amber", "High-risk breast screening plan (chest radiation)", "open_required_form",
                "Chest-wall radiation at age %d. Annual CBE and annual mammography+MRI begin at age %d%s." %
                (age_rad, start, (" (first imaging ~%s)" % due.isoformat()) if due else ""),
                facts_used={**fu, "first_imaging_due": due.isoformat() if due else None},
                action_payload=required_form_action(step="screening_test", section="Breast CBE"))


def map_bc_screening_high_risk_previous_breast_cancer(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("breast_previous_cancer")) != "yes":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    lat = str(facts.get("breast_previous_cancer_laterality") or "").lower()
    fu = {"laterality": lat or None}
    if lat not in ("left", "right", "bilateral"):
        return _rec("amber", "Record previous breast-cancer laterality", "open_required_form",
                    "Previous breast cancer: record laterality (left/right/bilateral) before a contralateral "
                    "surveillance recommendation can be made.", facts_used=fu,
                    action_payload=required_form_action(step="register_client",
                    section="Breast cancer risk assessment and history",
                    required_fields=["breast_previous_cancer_laterality"],
                    missing_fields=["breast_previous_cancer_laterality"]))
    interval = _num(facts.get("breast_high_risk_cbe_interval_months"))
    if lat == "bilateral":
        return _rec("amber", "Bilateral previous breast cancer: specialist surveillance", "open_required_form",
                    "Bilateral primary breast cancer — do not label 'contralateral'. Record and follow the documented "
                    "specialist surveillance plan.", facts_used=fu,
                    action_payload=required_form_action(step="screening_test", section="Breast screening plan",
                    required_fields=["breast_specialist_screening_plan"], missing_fields=["breast_specialist_screening_plan"]))
    if interval not in (6, 12):
        return _rec("amber", "Select CBE interval (6 or 12 months)", "open_required_form",
                    "Previous unilateral breast cancer: screen the contralateral breast — CBE every 6-12 months and "
                    "annual mammography. Choose 6 or 12 months before the CBE appointment is created.",
                    facts_used=fu, action_payload=required_form_action(step="screening_test",
                    section="Breast screening plan", required_fields=["breast_high_risk_cbe_interval_months"],
                    missing_fields=["breast_high_risk_cbe_interval_months"]))
    base = facts.get("last_mammography_date")
    if base:
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Contralateral breast annual mammography",
                                  interval_value=1, interval_unit="years", base_date=base,
                                  base_date_source="last_mammography_date",
                                  reason="Previous breast cancer, contralateral surveillance")
        return _rec("amber", "Contralateral breast surveillance: CBE %d-monthly + annual mammography" % int(interval),
                    "schedule_followup",
                    "Previous %s breast cancer. Screen the contralateral breast: CBE every %d months and annual "
                    "mammography." % (lat, int(interval)),
                    facts_used={**fu, "cbe_interval_months": int(interval), "base_date": base}, action_payload=payload)
    return _rec("amber", "Contralateral breast surveillance due now", "open_required_form",
                "Previous %s breast cancer: screen the contralateral breast — CBE every %d months and annual "
                "mammography. No mammogram date on record — due now." % (lat, int(interval)),
                facts_used=fu, action_payload=required_form_action(step="screening_test", section="Mammography"))


def map_bc_screening_high_risk_known_mutation(facts: dict) -> dict:
    if normalize_yes_no_unknown(facts.get("breast_known_pathogenic_mutation")) != "yes":
        return _rec("silent", "n/a", "no_action_required", "", facts_used={})
    fu = {"mutation": facts.get("breast_pathogenic_mutation_type")}
    plan = facts.get("breast_specialist_screening_plan")
    if not plan:
        return _rec("amber", "Known mutation: refer for specialist/genetic assessment", "create_referral",
                    "Known pathogenic mutation increasing breast-cancer risk. Refer for specialist/genetic "
                    "assessment. A mutation-specific imaging schedule is NOT invented; record the specialist plan "
                    "and schedule only from it.", facts_used=fu,
                    action_payload=referral_action(reason="genetic_counselling", urgency="routine",
                    department="medical_genetics",
                    requested_evaluation=["specialist/genetic assessment", "define surveillance imaging plan"],
                    note="Known pathogenic mutation. Establish a specialist surveillance plan before scheduling imaging."))
    base = facts.get("breast_specialist_plan_date") or facts.get("last_mammography_date")
    iv = _num(facts.get("breast_specialist_screening_interval_months"))
    if iv and base:
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Specialist breast surveillance (recorded plan)",
                                  interval_value=int(iv), interval_unit="months", base_date=base,
                                  base_date_source="breast_specialist_plan_date",
                                  reason="Known mutation, specialist-defined interval")
        if payload:
            return _rec("amber", "Breast surveillance per recorded specialist plan", "schedule_followup",
                        "Scheduling from the recorded specialist plan: every %d months (modalities: %s)." %
                        (int(iv), facts.get("breast_specialist_screening_modalities") or "as documented"),
                        facts_used={**fu, "interval_months": int(iv)}, action_payload=payload)
    return _rec("amber", "Known mutation: record specialist screening interval", "open_required_form",
                "Specialist plan recorded. Enter the specialist screening interval (months) and plan date to schedule.",
                facts_used=fu, action_payload=required_form_action(step="screening_test", section="Breast screening plan",
                required_fields=["breast_specialist_screening_interval_months", "breast_specialist_plan_date"],
                missing_fields=["breast_specialist_screening_interval_months"]))


def map_bc_genetics_referral(facts: dict) -> dict:
    g = derive_breast_genetics_referral(facts)
    if not g["eligible"]:
        return _rec("silent", "Genetics referral not indicated", "no_action_required", "",
                    facts_used={"criteria_met": []})
    return _rec("amber", "Refer for genetic counselling", "create_referral",
                "Meets hereditary breast/ovarian cancer criteria (%s). Refer for genetic counselling and hereditary "
                "cancer risk assessment. High-risk screening is not suppressed while this is pending." %
                ", ".join(g["criteria_met"]),
                facts_used={"criteria_met": g["criteria_met"]},
                action_payload=referral_action(reason="genetic_counselling", urgency="routine",
                department="medical_genetics",
                requested_evaluation=["genetic counselling", "hereditary cancer risk assessment",
                                      "consideration of genetic testing"],
                note="Genetic-counselling referral (criteria: %s)." % ", ".join(g["criteria_met"])))


def map_bc_cbe_abnormal(facts: dict) -> dict:
    sym = derive_breast_symptomatic(facts)
    if not sym["symptomatic"]:
        return _rec("silent", "CBE not abnormal", "no_action_required", "", facts_used={})
    fu = {"cbe_findings": sym["reasons"], "laterality": facts.get("breast_cbe_laterality")}
    payload = referral_action(reason="abnormal_breast_exam", urgency="priority", department="breast_surgery",
                              requested_evaluation=["clinical review", "diagnostic mammography and/or ultrasound",
                                                    "tissue diagnosis if indicated"],
                              note="Abnormal/symptomatic breast examination (%s). Arrange diagnostic imaging and "
                                   "referral per local capability." % ", ".join(sym["reasons"]))
    payload["form_prefill"] = {"breast_additional_imaging_required": "yes"}
    payload["target_workflow_step"] = "diagnostic_assessment"
    payload["target_section"] = "Breast Diagnostic Imaging"
    return _rec("amber", "Abnormal breast exam — diagnostic evaluation", "create_referral",
                "Abnormal or symptomatic CBE. Do not offer a routine screening interval. Recommend diagnostic imaging "
                "(mammography and/or ultrasound) and referral; obtain tissue diagnosis if indicated.",
                facts_used=fu, action_payload=payload)


def map_bc_mammography_birads(facts: dict) -> dict:
    b = str(facts.get("mammography_birads") or "").upper().replace("-", "_").replace(" ", "_")
    mdate = facts.get("mammography_date")
    fu = {"mammography_birads": b or None, "mammography_date": mdate}
    if b in ("", "PENDING", "NOT_DONE"):
        return _rec("silent", "No BI-RADS decision", "no_action_required", "", facts_used=fu)
    if b == "BI_RADS_0":
        return _rec("amber", "BI-RADS 0: additional imaging required", "open_required_form",
                    "Incomplete mammographic assessment. Arrange additional imaging using the modality/views "
                    "recommended by radiology. BI-RADS 0 is not a negative result.",
                    facts_used=fu, action_payload=required_form_action(step="diagnostic_assessment",
                    section="Breast Diagnostic Imaging", form_prefill={"breast_additional_imaging_required": "yes"}))
    if b in ("BI_RADS_1", "BI_RADS_2"):
        # resume the woman's active risk-based interval; do NOT force annual for a 2-year band
        elig = derive_breast_average_risk_eligibility(facts)
        band = elig.get("age_band")
        if elig["eligible"] and band and band["interval_value"] and mdate:
            payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                      service_name="Routine breast mammography",
                                      interval_value=band["interval_value"], interval_unit=band["interval_unit"],
                                      base_date=mdate, base_date_source="mammography_date",
                                      reason="BI-RADS %s: resume risk-based interval" % b[-1])
            if payload:
                return _rec("green", "BI-RADS %s: resume risk-based screening" % b[-1], "schedule_followup",
                            "No immediate diagnostic escalation. Continue the active breast screening schedule "
                            "(every %d %s for this age/risk band), using the mammography date as the base date." %
                            (band["interval_value"], band["interval_unit"]),
                            facts_used=fu, action_payload=payload)
        return _rec("green", "BI-RADS %s: resume risk-based screening" % b[-1], "no_action_required",
                    "No immediate diagnostic escalation. Continue the active breast screening schedule according to "
                    "the woman's age and risk category (do not force annual for a 2-year band).", facts_used=fu)
    if b == "BI_RADS_3":
        if not mdate:
            return _rec("amber", "Record the mammography date", "open_required_form",
                        "BI-RADS 3 needs a 3-month short-interval review, but the mammography date is missing. Enter it "
                        "to calculate the due date (never calculated from today).", facts_used=fu,
                        action_payload=required_form_action(step="screening_test", section="Mammography",
                        required_fields=["mammography_date"], missing_fields=["mammography_date"]))
        payload = schedule_action(step="followup_surveillance", section="Follow-up",
                                  service_name="Short-interval breast imaging review", interval_value=3,
                                  interval_unit="months", base_date=mdate, base_date_source="mammography_date",
                                  reason="BI-RADS 3: probably benign, 3-month review")
        return _rec("amber", "BI-RADS 3: short-interval review in 3 months", "schedule_followup",
                    "Probably benign. Review with repeat imaging in 3 months.", facts_used=fu, action_payload=payload)
    if b in ("BI_RADS_4", "BI_RADS_5"):
        red = b == "BI_RADS_5"
        return _rec("red" if red else "amber",
                    "BI-RADS %s: refer for core biopsy" % b[-1], "create_referral",
                    "Refer to breast surgery for core biopsy and histopathological diagnosis.", blocking=red,
                    facts_used=fu, action_payload=referral_action(reason="breast_core_biopsy",
                    urgency="urgent" if red else "priority", department="breast_surgery",
                    requested_evaluation=["breast surgical review", "core biopsy", "histopathology"],
                    note="BI-RADS %s mammogram. Refer for core biopsy and histopathological diagnosis." % b[-1]))
    return _rec("silent", "No BI-RADS decision", "no_action_required", "", facts_used=fu)


def map_bc_histopathology_interpretation(facts: dict) -> dict:
    r = str(facts.get("breast_histopathology_result") or "").lower()
    fu = {"breast_histopathology_result": r or None}
    if r in ("", "pending", "not_done"):
        return _rec("silent", "Awaiting breast histopathology", "no_action_required", "", facts_used=fu)
    if r == "negative_for_malignancy":
        return _rec("amber", "Breast histology negative: concordance review", "create_referral",
                    "Refer to the breast surgeon for discussion with the patient and radiology-pathology concordance "
                    "review. Do not discharge solely because histology is negative.",
                    facts_used=fu, action_payload=referral_action(reason="breast_pathology_review", urgency="routine",
                    department="breast_surgery", requested_evaluation=["review pathology result",
                    "assess imaging-pathology concordance", "discuss next steps with patient"],
                    note="Negative breast histology — arrange radiology-pathology concordance review."))
    if r in ("indeterminate", "inadequate"):
        return _rec("amber", "Breast histology %s: repeat biopsy" % r, "create_referral",
                    "Arrange repeat image-guided or excisional biopsy for definitive histopathology.",
                    facts_used=fu, action_payload=referral_action(reason="repeat_breast_biopsy", urgency="priority",
                    department="breast_surgery", requested_evaluation=["repeat image-guided biopsy or excisional biopsy",
                    "definitive histopathology"], note="%s breast histology — repeat biopsy for definitive diagnosis." % r))
    if r == "malignant":
        payload = referral_action(reason="confirmed_breast_cancer", urgency="urgent", department="oncology",
                                  requested_evaluation=["radiological staging", "breast cancer MDT discussion",
                                                        "definitive treatment planning"],
                                  note="Confirmed breast malignancy. Arrange radiological staging and refer for MDT "
                                       "discussion and onward treatment (single coordinated referral).")
        payload["form_prefill"] = {"breast_staging_imaging_status": "requested", "breast_mdt_status": "referred"}
        return _rec("red", "Malignant breast histology: staging + MDT referral", "create_referral",
                    "Arrange radiological staging and refer for multidisciplinary-team discussion and onward "
                    "treatment.", blocking=True, facts_used=fu, action_payload=payload)
    return _rec("silent", "No histopathology decision", "no_action_required", "", facts_used=fu)


_DISPATCH.update({
    "bc.risk.classification": (map_bc_risk_classification, None),
    "bc.screening.average_risk": (map_bc_screening_average_risk, None),
    "bc.screening.high_risk.family_history": (map_bc_screening_high_risk_family_history,
                                              "breast_first_degree_relative_affected"),
    "bc.screening.high_risk.abnormal_biopsy": (map_bc_screening_high_risk_abnormal_biopsy,
                                               "breast_previous_abnormal_biopsy"),
    "bc.screening.high_risk.chest_radiation": (map_bc_screening_high_risk_chest_radiation,
                                               "breast_previous_chest_wall_radiation"),
    "bc.screening.high_risk.previous_breast_cancer": (map_bc_screening_high_risk_previous_breast_cancer,
                                                      "breast_previous_cancer"),
    "bc.screening.high_risk.known_mutation": (map_bc_screening_high_risk_known_mutation,
                                              "breast_known_pathogenic_mutation"),
    "bc.genetics.referral": (map_bc_genetics_referral, None),
    "bc.cbe.abnormal": (map_bc_cbe_abnormal, "breast_cbe_result"),
    "bc.mammography.birads": (map_bc_mammography_birads, "mammography_birads"),
    "bc.histopathology.interpretation": (map_bc_histopathology_interpretation, "breast_histopathology_result"),
})
