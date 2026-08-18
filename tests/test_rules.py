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
        "hpv_result": "negative",
        "hiv_status": "positive",
        "sample_date": "2026-08-11",
        "result_date": "2026-08-20"
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
        "cytology_result": "ASC_US",
        "hr_hpv_triage_result": "positive",
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
        "hpv_result": "not_recorded",
        "hiv_status": "unknown"
    }
    response = client.post("/api/v1/rules/cc.hpv.interpretation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["fired"] is False
    assert data["message"] == "No recommendation for those inputs"