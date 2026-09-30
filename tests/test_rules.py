"""
Unit tests for Cervical and Breast Cancer Guideline Rules API.
Run with: pytest
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from packages import curated_cds

client = TestClient(app)


# =====================================================================
# 1. DIRECT ENGINE TESTS (curated_cds.evaluate / map_*)
# =====================================================================

def test_hpv_negative_hiv_positive_rescreen_3_years():
    facts = {
        "hpv_result": "negative",
        "hiv_status": "positive",
        "hpv_sample_collection_date": "2026-08-11"
    }
    result = curated_cds.map_hpv(facts)
    assert result["severity_class"] == "green"
    assert "3 years" in result["recommendation_text"]
    assert result["action_code"] == "schedule_followup"


def test_hpv_positive_requires_triage():
    facts = {
        "hpv_result": "positive",
        "hiv_status": "positive"
    }
    result = curated_cds.map_hpv(facts)
    assert result["severity_class"] == "amber"
    assert result["action_code"] == "open_required_form"
    assert "Triage HPV-positive" in result["recommendation_text"]


def test_via_pregnancy_second_trimester_deferred():
    facts = {
        "woman_very_ill": "no",
        "pregnancy_status": "pregnant",
        "gestational_age_weeks": 20,
        "postpartum_status": "no",
        "mass_suspicious_for_invasive_disease": "no",
        "history_treatment_precancer_or_cancer": "no",
        "known_allergy_to_acetic_acid": "no",
        "history_total_hysterectomy": "no"
    }
    result = curated_cds.map_via_eligibility(facts)
    assert result["severity_class"] == "amber"
    assert "2nd/3rd trimester" in result["recommendation_text"]
    assert result["action_code"] == "open_required_form"


def test_ablation_all_criteria_met():
    facts = {
        f"ablation_c{i}_{name}": "yes"
        for i, name in enumerate([
            "positive_screen_or_eligible_precancer",
            "entire_lesion_and_margins_visible",
            "lesion_lte_75_percent",
            "no_canal_gt2mm_or_vaginal_extension",
            "probe_full_coverage_no_gap_gt2mm",
            "no_suspicion_invasive_cancer",
            "no_active_pid_cervicitis_or_polyp",
            "not_pregnant_and_postpartum_6w_or_more",
            "no_prior_precancer_treatment",
            "informed_consent_given"
        ], start=1)
    }
    result = curated_cds.map_eligibility(facts)
    assert result["severity_class"] == "green"
    assert "Eligible for ablative treatment" in result["recommendation_text"]


def test_breast_high_risk_classification():
    facts = {
        "breast_previous_cancer": "yes",
        "breast_cbe_result": "normal"
    }
    result = curated_cds.map_bc_risk_classification(facts)
    assert result["severity_class"] == "amber"
    assert "HIGH RISK" in result["recommendation_text"]


# =====================================================================
# 2. FASTAPI ENDPOINT TESTS (TestClient)
# =====================================================================

def test_catalog_endpoint():
    response = client.get("/api/v1/rules/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["total_rules"] >= 15
    assert len(data["rules"]) >= 15


def test_api_hpv_endpoint_fires():
    payload = {
        "patient_id": "test-patient-001",
        "HPV Test Findings": "Negative",
        "HIV Status": "Positive",
        "Sample Date": "2026-08-11",
        "Result Date": "2026-08-20"
    }
    response = client.post("/api/v1/rules/cc.hpv.interpretation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["fired"] is True
    assert data["severity"] == "green"
    assert "3 years" in data["recommendation"]


def test_api_cytology_ascus_hpv_positive_endpoint():
    payload = {
        "patient_id": "test-patient-002",
        "Pap Smear": "ASCUS(Atypical squamous cells of undetermined significance)",
        "HPV Test Findings": "Positive",
        "cytology_sample_date": "2026-08-11"
    }
    response = client.post("/api/v1/rules/cc.cytology.interpretation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["fired"] is True
    assert data["action_code"] == "create_referral"
    assert "Colposcopy" in data["recommendation"]


def test_api_silent_input_returns_no_recommendation():
    payload = {
        "patient_id": "test-patient-003",
        "HPV Test Findings": "not_recorded",
        "HIV Status": "Unknown"
    }
    response = client.post("/api/v1/rules/cc.hpv.interpretation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["fired"] is False
    assert data["message"] == "No recommendation for those inputs"

# =====================================================================
# 3. THE DATA DICTIONARY CONTRACT
# =====================================================================

BASE = "/api/v1/rules/"


def test_every_curated_rule_has_an_endpoint():
    """A rule the engine can evaluate but nothing can call is a rule nobody gets."""
    exposed = {r.path.rsplit("/", 1)[-1] for r in app.routes
               if "POST" in getattr(r, "methods", set())}
    assert set(curated_cds._DISPATCH) - exposed == set()


@pytest.mark.parametrize("rule_id", sorted(curated_cds._DISPATCH))
def test_every_endpoint_answers_on_its_defaults(rule_id):
    assert client.post(BASE + rule_id, json={}).status_code == 200


def test_answers_are_matched_whatever_the_casing():
    """A capital letter must never decide whether a woman gets advice."""
    form = {"HPV Test Findings": "Negative", "HIV Status": "Positive", "Sample Date": "2026-08-11"}
    lower = {k: (v.lower() if k != "Sample Date" else v) for k, v in form.items()}
    a = client.post(BASE + "cc.hpv.interpretation", json=form).json()
    b = client.post(BASE + "cc.hpv.interpretation", json=lower).json()
    assert a["recommendation"] == b["recommendation"] == "Re-screen after 3 years"


def test_the_old_short_field_names_are_rejected():
    """Silently ignoring them would answer from the schema defaults instead of the data."""
    r = client.post(BASE + "cc.hpv.interpretation", json={"hpv_result": "Negative"})
    assert r.status_code == 422


def test_an_answer_the_rule_does_not_know_is_rejected():
    r = client.post(BASE + "cc.hpv.interpretation", json={"HIV Status": "reactive"})
    assert r.status_code == 422


def test_breast_high_risk_endpoints_fire():
    d = client.post(BASE + "bc.screening.high_risk.family_history", json={
        "breast_first_degree_relative_affected": "yes", "breast_first_degree_relatives_count": 1,
        "breast_youngest_family_case_age": 40, "Client Age": 35}).json()
    assert d["fired"] is True
    assert d["action_code"] in ("schedule_followup", "open_required_form")


def test_birads_5_is_red_and_blocking():
    d = client.post(BASE + "bc.mammography.birads", json={
        "Mammogram – BI-RADS": "BI-RADS 5", "mammography_date": "2026-08-11"}).json()
    assert d["fired"] is True
    assert d["severity"] == "red"
    assert d["complete_card"]["blocking"] is True


def test_the_card_reports_facts_in_dictionary_terms():
    """The reply is read next to the request, so it uses the same names and wording."""
    d = client.post(BASE + "cc.hpv.interpretation", json={
        "HPV Test Findings": "negative", "HIV Status": "Positive", "Sample Date": "2026-08-11"}).json()
    assert d["facts_used"]["HPV Test Findings"] == "Negative"
    assert d["facts_used"]["HIV Status"] == "Positive"
