"""
Kenya Cervical and Breast Cancer Guideline Rules API
Includes 15 Cervical Cancer rules and 2 Breast Cancer rules.
"""
from enum import Enum
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Import Dr. Fred's curated CDS package
from packages import curated_cds

app = FastAPI(
    title="Kenya Cervical and Breast Cancer Guideline Rules API",
    version="1.0.0",
    description="Dedicated decision support endpoints for Kenya MOH Cervical and Breast Cancer Screening Guidelines."
)

# =====================================================================
# MASTER DROPDOWN ENUMS
# =====================================================================

# --- Cervical Enums ---
class HpvResultEnum(str, Enum):
    not_recorded = "not_recorded"
    negative = "negative"
    positive = "positive"
    invalid_or_unsatisfactory = "invalid_or_unsatisfactory"

class HivStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    positive = "positive"
    negative = "negative"
    unknown = "unknown"
    not_disclosed = "not_disclosed"

class ViaResultEnum(str, Enum):
    not_recorded = "not_recorded"
    via_negative = "VIA_NEGATIVE"
    via_positive = "VIA_POSITIVE"
    suspicious = "SUSPICIOUS_FOR_CANCER"
    inadequate = "INADEQUATE_UNSATISFACTORY"

class CytologyResultEnum(str, Enum):
    not_recorded = "not_recorded"
    nilm = "NILM"
    ascus = "ASC_US"
    lsil = "LSIL"
    hsil = "HSIL"
    unsatisfactory = "UNSATISFACTORY"

class ColposcopyResultEnum(str, Enum):
    not_recorded = "not_recorded"
    negative = "COLPOSCOPY_NEGATIVE"
    positive = "COLPOSCOPY_POSITIVE"
    suspicious = "SUSPICIOUS_FOR_CANCER"
    inadequate = "INADEQUATE_COLPOSCOPY"

class BiopsyResultEnum(str, Enum):
    not_recorded = "not_recorded"
    normal = "BENIGN_OR_NORMAL"
    cin1 = "CIN1"
    cin2 = "CIN2"
    cin3 = "CIN3"
    ais = "AIS"
    cancer = "INVASIVE_CANCER"

class YesNoEnum(str, Enum):
    not_recorded = "not_recorded"
    yes = "yes"
    no = "no"

class PregnancyStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    pregnant = "pregnant"
    not_pregnant = "not_pregnant"

class MenopausalStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    postmenopausal = "postmenopausal"
    premenopausal = "premenopausal"

class HysterectomyIndicationEnum(str, Enum):
    not_recorded = "not_recorded"
    benign = "benign_or_non_cervical"
    high_grade = "high_grade_cin_or_hsil"
    cancer = "cervical_cancer"
    unknown = "unknown"

class VaccinationStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    vaccinated = "vaccinated"
    partially_vaccinated = "partially_vaccinated"
    unvaccinated = "unvaccinated"

class ScreeningMethodEnum(str, Enum):
    not_recorded = "not_recorded"
    hpv = "hpv"
    cytology = "cytology"
    via = "via"

# --- Breast Enums ---
class BreastCbeResultEnum(str, Enum):
    not_recorded = "not_recorded"
    normal = "normal"
    abnormal = "abnormal"

class BreastSharedDecisionEnum(str, Enum):
    not_recorded = "not_recorded"
    continue_screening = "continue"
    stop = "stop"
    defer = "defer"

class HrHpvTriageResultEnum(str, Enum):
    not_recorded = "not_recorded"
    positive = "positive"
    negative = "negative"
    not_applicable = "not_applicable"


# REQUEST SCHEMAS


# ---------------- CERVICAL CANCER SCHEMAS (15 RULES) ----------------

class HpvInterpretationRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    hpv_result: HpvResultEnum = Field(HpvResultEnum.negative, description="PRIMARY: Select HPV Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.positive, description="DEPENDENT: Select HIV Status")
    sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Collection Date (YYYY-MM-DD)")
    result_date: Optional[str] = Field("2026-08-20", description="DEPENDENT: Result Available Date (YYYY-MM-DD)")

class ViaEligibilityRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    via_exam_date: Optional[str] = Field("2026-08-11", description="PRIMARY: VIA Exam Date (YYYY-MM-DD)")
    woman_very_ill: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Woman Very Ill")
    pregnancy_status: PregnancyStatusEnum = Field(PregnancyStatusEnum.not_recorded, description="DEPENDENT: Pregnancy Status")
    gestational_age_weeks: Optional[int] = Field(None, description="DEPENDENT: Gestational Age (weeks)")
    postpartum_status: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Postpartum")
    postpartum_weeks_since_delivery: Optional[int] = Field(None, description="DEPENDENT: Weeks Since Delivery")
    mass_suspicious_for_invasive_disease: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Suspicious Cervical Mass")
    history_treatment_precancer_or_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior Precancer/Cancer Treatment")
    known_allergy_to_acetic_acid: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Known Acetic Acid Allergy")
    history_total_hysterectomy: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Total Hysterectomy")

class ViaInterpretationRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    via_result: ViaResultEnum = Field(ViaResultEnum.via_negative, description="PRIMARY: Select VIA Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.negative, description="DEPENDENT: Select HIV Status")
    via_exam_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: VIA Exam Date (YYYY-MM-DD)")

class CytologyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    cytology_result: CytologyResultEnum = Field(CytologyResultEnum.nilm, description="PRIMARY: Select Cytology Result")
    hr_hpv_triage_result: HrHpvTriageResultEnum = Field(HrHpvTriageResultEnum.not_recorded, description="DEPENDENT: HR-HPV Triage Result")
    cytology_sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Date (YYYY-MM-DD)")

class ColposcopyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    colposcopy_result: ColposcopyResultEnum = Field(ColposcopyResultEnum.negative, description="PRIMARY: Select Colposcopy Result")
    biopsy_kit_available: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Biopsy Kit Available")
    biopsy_done: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Biopsy Done")
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.not_recorded, description="DEPENDENT: Biopsy Result")
    colposcopy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Colposcopy Date (YYYY-MM-DD)")

class ColposcopySurveillanceRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

class PersistentHpvRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

class HistologyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.cin2, description="PRIMARY: Select Biopsy Result")
    biopsy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Biopsy Date (YYYY-MM-DD)")

class AblationEligibilityRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    ablation_c1_positive_screen_or_eligible_precancer: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 1: Positive Screen")
    ablation_c2_entire_lesion_and_margins_visible: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 2: Entire Lesion Visible")
    ablation_c3_lesion_lte_75_percent: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 3: Lesion <= 75%")
    ablation_c4_no_canal_gt2mm_or_vaginal_extension: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 4: No Canal Extension")
    ablation_c5_probe_full_coverage_no_gap_gt2mm: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 5: Full Probe Coverage")
    ablation_c6_no_suspicion_invasive_cancer: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 6: No Suspicion of Cancer")
    ablation_c7_no_active_pid_cervicitis_or_polyp: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 7: No Active PID")
    ablation_c8_not_pregnant_and_postpartum_6w_or_more: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 8: Not Pregnant / Postpartum 6w+")
    ablation_c9_no_prior_precancer_treatment: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 9: No Prior Treatment")
    ablation_c10_informed_consent_given: YesNoEnum = Field(YesNoEnum.yes, description="Criterion 10: Informed Consent Given")

class PregnancyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    pregnancy_status: PregnancyStatusEnum = Field(PregnancyStatusEnum.pregnant, description="PRIMARY: Select Pregnancy Status")
    gestational_age_weeks: Optional[int] = Field(10, description="DEPENDENT: Gestational Age in Weeks")
    mass_suspicious_for_invasive_disease: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Suspicious Cervical Mass")
    precancer_treatment_indicated: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Precancer Treatment Indicated")
    date_of_delivery: Optional[str] = Field(None, description="DEPENDENT: Expected Delivery Date (YYYY-MM-DD)")

class PostpartumRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    postpartum_status: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Postpartum Status")
    postpartum_weeks_since_delivery: int = Field(4, description="DEPENDENT: Weeks Postpartum")
    date_of_delivery: Optional[str] = Field("2026-07-14", description="DEPENDENT: Date of Delivery (YYYY-MM-DD)")

class HysterectomyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    history_total_hysterectomy: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Total Hysterectomy?")
    hysterectomy_indication: HysterectomyIndicationEnum = Field(HysterectomyIndicationEnum.benign, description="DEPENDENT: Indication")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")

class HpvVaccinatedRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    hpv_vaccination_status: VaccinationStatusEnum = Field(VaccinationStatusEnum.vaccinated, description="PRIMARY: HPV Vaccination Status")

class PostmenopausalRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    menopausal_status: MenopausalStatusEnum = Field(MenopausalStatusEnum.postmenopausal, description="PRIMARY: Menopausal Status")
    age_years: Optional[int] = Field(55, description="DEPENDENT: Age in Years")
    screening_method: ScreeningMethodEnum = Field(ScreeningMethodEnum.hpv, description="DEPENDENT: Screening Method")
    cytology_sample_date: Optional[str] = Field(None, description="DEPENDENT: Cytology Sample Date (YYYY-MM-DD)")
    hpv_sample_collection_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: HPV Sample Date (YYYY-MM-DD)")

class Age65PlusRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    age_years: int = Field(68, description="PRIMARY: Patient Age (>=65)")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")
    negative_hpv_tests_last_10_years: Optional[int] = Field(2, description="DEPENDENT: Negative HPV Tests Last 10 Yrs")
    negative_pap_tests_last_10_years: Optional[int] = Field(0, description="DEPENDENT: Negative Pap Tests Last 10 Yrs")
    screening_history_complete_for_age65_exit_assessment: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Screening History Complete")


# ---------------- BREAST CANCER SCHEMAS (2 RULES) ----------------

class BreastRiskClassificationRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    breast_first_degree_relative_affected: YesNoEnum = Field(YesNoEnum.no, description="First-degree relative with breast cancer")
    breast_previous_abnormal_biopsy: YesNoEnum = Field(YesNoEnum.no, description="Previous abnormal breast biopsy")
    breast_previous_chest_wall_radiation: YesNoEnum = Field(YesNoEnum.no, description="Previous chest wall radiation before age 30")
    breast_previous_cancer: YesNoEnum = Field(YesNoEnum.no, description="Personal history of breast cancer")
    breast_known_pathogenic_mutation: YesNoEnum = Field(YesNoEnum.no, description="Known BRCA1/BRCA2 or other mutation")
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.normal, description="Clinical Breast Exam Result")

class BreastAverageRiskScreeningRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    date_of_birth: Optional[str] = Field("1982-05-15", description="Patient Date of Birth (YYYY-MM-DD)")
    age_years: Optional[int] = Field(44, description="Patient Age in Years")
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.normal, description="Clinical Breast Exam Result")
    breast_screening_shared_decision: BreastSharedDecisionEnum = Field(BreastSharedDecisionEnum.not_recorded, description="Shared Decision for Age 75+")



# CORE EVALUATION HELPERS


def _execute_cervical_rule_eval(rule_id: str, raw_facts: dict, patient_id: str):
    facts = {}
    
    # Clean inputs & cast numeric types
    for k, v in raw_facts.items():
        if v is not None and str(v) not in ("not_recorded", "string", ""):
            val = v.value if hasattr(v, "value") else v
            if k in ("gestational_age_weeks", "postpartum_weeks_since_delivery", "age_years",
                     "negative_hpv_tests_last_10_years", "negative_pap_tests_last_10_years"):
                try:
                    facts[k] = int(val)
                except (ValueError, TypeError):
                    facts[k] = val
            else:
                facts[k] = str(val)

    # Map aliases expected by  internal logic
    if "sample_date" in facts:
        facts["hpv_sample_collection_date"] = facts["sample_date"]
    if "result_date" in facts:
        facts["hpv_result_available_date"] = facts["result_date"]

    # Direct execution via _DISPATCH table
    fn_dep = curated_cds._DISPATCH.get(rule_id)
    if fn_dep:
        fn, _primary = fn_dep
        card = fn(facts)
        
        if card.get("severity_class") != "silent":
            return {
                "patient_id": patient_id,
                "rule_id": rule_id,
                "fired": True,
                "severity": card.get("severity_class"),
                "recommendation": card.get("recommendation_text") or card.get("card_title"),
                "reason": card.get("reason_text") or card.get("card_summary"),
                "action_code": card.get("action_code"),
                "facts_used": card.get("facts_used", facts),
                "guideline": card.get("guideline_page_refs", []),
                "complete_card": card
            }

    return {
        "patient_id": patient_id,
        "rule_id": rule_id,
        "fired": False,
        "message": "No recommendation for those inputs",
        "recommendation": None,
        "reason": None,
        "facts_evaluated": facts
    }



# API ENDPOINTS

@app.get("/api/v1/rules/catalog")
def get_rule_catalog():
    """Returns the catalog directly loaded from curated_cds."""
    return {
        "total_rules": len(curated_cds.catalog().get("rules", [])),
        "rules": curated_cds.catalog().get("rules", [])
    }


# ---------------- 15 CERVICAL CANCER ENDPOINTS ----------------

@app.post("/api/v1/rules/cc.hpv.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_hpv_rule(req: HpvInterpretationRequest):
    return _execute_cervical_rule_eval("cc.hpv.interpretation", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.via.eligibility", tags=["15 Cervical Cancer Rules"])
def evaluate_via_eligibility(req: ViaEligibilityRequest):
    return _execute_cervical_rule_eval("cc.via.eligibility", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.via.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_via_rule(req: ViaInterpretationRequest):
    return _execute_cervical_rule_eval("cc.via.interpretation", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.cytology.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_cytology_rule(req: CytologyRequest):
    return _execute_cervical_rule_eval("cc.cytology.interpretation", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.colposcopy.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_colposcopy_rule(req: ColposcopyRequest):
    return _execute_cervical_rule_eval("cc.colposcopy.interpretation", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.colposcopy.negative_surveillance", tags=["15 Cervical Cancer Rules"])
def evaluate_colposcopy_surveillance(req: ColposcopySurveillanceRequest):
    return _execute_cervical_rule_eval("cc.colposcopy.negative_surveillance", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.hpv.persistent_after_negative_colposcopy", tags=["15 Cervical Cancer Rules"])
def evaluate_persistent_hpv(req: PersistentHpvRequest):
    return _execute_cervical_rule_eval("cc.hpv.persistent_after_negative_colposcopy", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.histology.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_histology_rule(req: HistologyRequest):
    return _execute_cervical_rule_eval("cc.histology.interpretation", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.eligibility.exclusions", tags=["15 Cervical Cancer Rules"])
def evaluate_ablation_eligibility(req: AblationEligibilityRequest):
    return _execute_cervical_rule_eval("cc.eligibility.exclusions", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.pregnancy", tags=["15 Cervical Cancer Rules"])
def evaluate_pregnancy_rule(req: PregnancyRequest):
    return _execute_cervical_rule_eval("cc.special.pregnancy", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.postpartum", tags=["15 Cervical Cancer Rules"])
def evaluate_postpartum_rule(req: PostpartumRequest):
    return _execute_cervical_rule_eval("cc.special.postpartum", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.total_hysterectomy", tags=["15 Cervical Cancer Rules"])
def evaluate_hysterectomy_rule(req: HysterectomyRequest):
    return _execute_cervical_rule_eval("cc.special.total_hysterectomy", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.hpv_vaccinated", tags=["15 Cervical Cancer Rules"])
def evaluate_hpv_vaccinated(req: HpvVaccinatedRequest):
    return _execute_cervical_rule_eval("cc.special.hpv_vaccinated", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.postmenopausal", tags=["15 Cervical Cancer Rules"])
def evaluate_postmenopausal(req: PostmenopausalRequest):
    return _execute_cervical_rule_eval("cc.special.postmenopausal", req.dict(), req.patient_id)

@app.post("/api/v1/rules/cc.special.age_65_plus", tags=["15 Cervical Cancer Rules"])
def evaluate_age_65_plus(req: Age65PlusRequest):
    return _execute_cervical_rule_eval("cc.special.age_65_plus", req.dict(), req.patient_id)


# ---------------- 2 BREAST CANCER ENDPOINTS ----------------

@app.post("/api/v1/rules/bc.risk.classification", tags=["2 Breast Cancer Rules"])
def evaluate_breast_risk_classification(req: BreastRiskClassificationRequest):
    facts = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in req.dict().items()
        if k != "patient_id" and v is not None and str(v) not in ("not_recorded", "string", "")
    }
    card = curated_cds.map_bc_risk_classification(facts)
    
    if card.get("severity_class") != "silent":
        return {
            "patient_id": req.patient_id,
            "rule_id": "bc.risk.classification",
            "fired": True,
            "severity": card.get("severity_class"),
            "recommendation": card.get("recommendation_text"),
            "reason": card.get("reason_text"),
            "action_code": card.get("action_code"),
            "facts_used": card.get("facts_used", facts),
            "guideline": card.get("guideline_page_refs", ["kenya_ncsedg_2024_breast"]),
            "complete_card": card
        }

    return {
        "patient_id": req.patient_id,
        "rule_id": "bc.risk.classification",
        "fired": False,
        "message": "No recommendation for those inputs",
        "recommendation": None,
        "reason": None,
        "facts_evaluated": facts
    }


@app.post("/api/v1/rules/bc.screening.average_risk", tags=["2 Breast Cancer Rules"])
def evaluate_breast_average_risk_screening(req: BreastAverageRiskScreeningRequest):
    facts = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in req.dict().items()
        if k != "patient_id" and v is not None and str(v) not in ("not_recorded", "string", "")
    }
    if "age_years" in facts:
        try:
            facts["age_years"] = int(facts["age_years"])
        except (ValueError, TypeError):
            pass

    card = curated_cds.map_bc_screening_average_risk(facts)
    
    if card.get("severity_class") != "silent":
        return {
            "patient_id": req.patient_id,
            "rule_id": "bc.screening.average_risk",
            "fired": True,
            "severity": card.get("severity_class"),
            "recommendation": card.get("recommendation_text"),
            "reason": card.get("reason_text"),
            "action_code": card.get("action_code"),
            "facts_used": card.get("facts_used", facts),
            "guideline": card.get("guideline_page_refs", ["kenya_ncsedg_2024_breast"]),
            "complete_card": card
        }

    return {
        "patient_id": req.patient_id,
        "rule_id": "bc.screening.average_risk",
        "fired": False,
        "message": "No recommendation for those inputs",
        "recommendation": None,
        "reason": None,
        "facts_evaluated": facts
    }