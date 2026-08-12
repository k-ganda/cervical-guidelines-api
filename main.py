"""
Cervical Cancer Guideline Rules API
Complete, Audited 15-Rule API.
"""
from enum import Enum
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Import Dr. Fred's curated CDS package
from packages import curated_cds

app = FastAPI(
    title="Kenya Cervical Cancer Guideline Rules API",
    version="1.0.0",
    description="Dedicated endpoints with full field sets for all 15 Kenya MOH Cervical Cancer Rules."
)


# MASTER DROPDOWN ENUMS


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



# REQUEST SCHEMAS (FULL FIELD SETS FOR ALL 15 RULES)


# 1. HPV Interpretation
class HpvInterpretationRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    hpv_result: HpvResultEnum = Field(HpvResultEnum.negative, description="PRIMARY: Select HPV Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.positive, description="DEPENDENT: Select HIV Status")
    sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Collection Date (YYYY-MM-DD)")
    result_date: Optional[str] = Field("2026-08-20", description="DEPENDENT: Result Available Date (YYYY-MM-DD)")

# 2. VIA Eligibility Pre-check
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

# 3. VIA Interpretation
class ViaInterpretationRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    via_result: ViaResultEnum = Field(ViaResultEnum.via_negative, description="PRIMARY: Select VIA Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.negative, description="DEPENDENT: Select HIV Status")
    via_exam_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: VIA Exam Date (YYYY-MM-DD)")

# 4. Cytology Interpretation
class CytologyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    cytology_result: CytologyResultEnum = Field(CytologyResultEnum.nilm, description="PRIMARY: Select Cytology Result")
    hr_hpv_triage_result: HivStatusEnum = Field(HivStatusEnum.not_recorded, description="DEPENDENT: HR-HPV Triage Result")
    cytology_sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Date (YYYY-MM-DD)")

# 5. Colposcopy Interpretation
class ColposcopyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    colposcopy_result: ColposcopyResultEnum = Field(ColposcopyResultEnum.negative, description="PRIMARY: Select Colposcopy Result")
    biopsy_kit_available: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Biopsy Kit Available")
    biopsy_done: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Biopsy Done")
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.not_recorded, description="DEPENDENT: Biopsy Result")
    colposcopy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Colposcopy Date (YYYY-MM-DD)")

# 6. Negative Colposcopy HPV Surveillance
class ColposcopySurveillanceRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

# 7. Persistent HPV After Negative Colposcopy
class PersistentHpvRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

# 8. Histology Interpretation
class HistologyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.cin2, description="PRIMARY: Select Biopsy Result")
    biopsy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Biopsy Date (YYYY-MM-DD)")

# 9. Ablation Eligibility / Exclusions
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

# 10. Special Population — Pregnancy
class PregnancyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    pregnancy_status: PregnancyStatusEnum = Field(PregnancyStatusEnum.pregnant, description="PRIMARY: Select Pregnancy Status")
    gestational_age_weeks: Optional[int] = Field(10, description="DEPENDENT: Gestational Age in Weeks")
    mass_suspicious_for_invasive_disease: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Suspicious Cervical Mass")
    precancer_treatment_indicated: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Precancer Treatment Indicated")
    date_of_delivery: Optional[str] = Field(None, description="DEPENDENT: Expected Delivery Date (YYYY-MM-DD)")

# 11. Special Population — Postpartum
class PostpartumRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    postpartum_status: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Postpartum Status")
    postpartum_weeks_since_delivery: int = Field(4, description="DEPENDENT: Weeks Postpartum")
    date_of_delivery: Optional[str] = Field("2026-07-14", description="DEPENDENT: Date of Delivery (YYYY-MM-DD)")

# 12. Special Population — Total Hysterectomy
class HysterectomyRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    history_total_hysterectomy: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Total Hysterectomy?")
    hysterectomy_indication: HysterectomyIndicationEnum = Field(HysterectomyIndicationEnum.benign, description="DEPENDENT: Indication")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")

# 13. Special Population — HPV Vaccinated
class HpvVaccinatedRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    hpv_vaccination_status: VaccinationStatusEnum = Field(VaccinationStatusEnum.vaccinated, description="PRIMARY: HPV Vaccination Status")

# 14. Special Population — Postmenopausal
class PostmenopausalRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    menopausal_status: MenopausalStatusEnum = Field(MenopausalStatusEnum.postmenopausal, description="PRIMARY: Menopausal Status")
    age_years: Optional[int] = Field(55, description="DEPENDENT: Age in Years")
    screening_method: ScreeningMethodEnum = Field(ScreeningMethodEnum.hpv, description="DEPENDENT: Screening Method")
    cytology_sample_date: Optional[str] = Field(None, description="DEPENDENT: Cytology Sample Date (YYYY-MM-DD)")
    hpv_sample_collection_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: HPV Sample Date (YYYY-MM-DD)")

# 15. Special Population — Age 65+
class Age65PlusRequest(BaseModel):
    patient_id: str = "demo-patient-001"
    age_years: int = Field(68, description="PRIMARY: Patient Age (>=65)")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")
    negative_hpv_tests_last_10_years: Optional[int] = Field(2, description="DEPENDENT: Negative HPV Tests Last 10 Yrs")
    negative_pap_tests_last_10_years: Optional[int] = Field(0, description="DEPENDENT: Negative Pap Tests Last 10 Yrs")
    screening_history_complete_for_age65_exit_assessment: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Screening History Complete")



# CORE FACT RESOLVER & EVALUATOR WRAPPER


def _execute_rule_eval(rule_id: str, raw_facts: dict, patient_id: str):
    facts = {}
    
    # 1. Clean inputs & cast numeric types
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

    # 2. Map aliases expected by  internal logic
    if "sample_date" in facts:
        facts["hpv_sample_collection_date"] = facts["sample_date"]
    if "result_date" in facts:
        facts["hpv_result_available_date"] = facts["result_date"]

    # 3. Direct execution via _DISPATCH table
    fn_dep = curated_cds._DISPATCH.get(rule_id)
    if fn_dep:
        fn, _primary = fn_dep
        card = fn(facts)
        
        # If the rule produces an active card (not "silent")
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

    # "No recommendation" fallback when severity is "silent" or rule does not fire
    return {
        "patient_id": patient_id,
        "rule_id": rule_id,
        "fired": False,
        "message": "No recommendation for those inputs",
        "recommendation": None,
        "reason": None,
        "facts_evaluated": facts
    }


# API ENDPOINTS (All 15 Rules)


@app.get("/api/v1/rules/catalog")
def get_rule_catalog():
    """Returns the catalog directly loaded from curated_cds."""
    return {"total_rules": len(curated_cds.catalog().get("rules", [])), "rules": curated_cds.catalog().get("rules", [])}

# 1. HPV interpretation
@app.post("/api/v1/rules/cc.hpv.interpretation", tags=["15 Individual Guideline Rules"])
def evaluate_hpv_rule(req: HpvInterpretationRequest):
    return _execute_rule_eval("cc.hpv.interpretation", req.dict(), req.patient_id)

# 2. VIA eligibility pre-check
@app.post("/api/v1/rules/cc.via.eligibility", tags=["15 Individual Guideline Rules"])
def evaluate_via_eligibility(req: ViaEligibilityRequest):
    return _execute_rule_eval("cc.via.eligibility", req.dict(), req.patient_id)

# 3. VIA interpretation
@app.post("/api/v1/rules/cc.via.interpretation", tags=["15 Individual Guideline Rules"])
def evaluate_via_rule(req: ViaInterpretationRequest):
    return _execute_rule_eval("cc.via.interpretation", req.dict(), req.patient_id)

# 4. Cytology interpretation
@app.post("/api/v1/rules/cc.cytology.interpretation", tags=["15 Individual Guideline Rules"])
def evaluate_cytology_rule(req: CytologyRequest):
    return _execute_rule_eval("cc.cytology.interpretation", req.dict(), req.patient_id)

# 5. Colposcopy interpretation
@app.post("/api/v1/rules/cc.colposcopy.interpretation", tags=["15 Individual Guideline Rules"])
def evaluate_colposcopy_rule(req: ColposcopyRequest):
    return _execute_rule_eval("cc.colposcopy.interpretation", req.dict(), req.patient_id)

# 6. Negative-colposcopy HPV surveillance
@app.post("/api/v1/rules/cc.colposcopy.negative_surveillance", tags=["15 Individual Guideline Rules"])
def evaluate_colposcopy_surveillance(req: ColposcopySurveillanceRequest):
    return _execute_rule_eval("cc.colposcopy.negative_surveillance", req.dict(), req.patient_id)

# 7. Persistent HPV after negative colposcopy
@app.post("/api/v1/rules/cc.hpv.persistent_after_negative_colposcopy", tags=["15 Individual Guideline Rules"])
def evaluate_persistent_hpv(req: PersistentHpvRequest):
    return _execute_rule_eval("cc.hpv.persistent_after_negative_colposcopy", req.dict(), req.patient_id)

# 8. Histology interpretation
@app.post("/api/v1/rules/cc.histology.interpretation", tags=["15 Individual Guideline Rules"])
def evaluate_histology_rule(req: HistologyRequest):
    return _execute_rule_eval("cc.histology.interpretation", req.dict(), req.patient_id)

# 9. Ablation eligibility
@app.post("/api/v1/rules/cc.eligibility.exclusions", tags=["15 Individual Guideline Rules"])
def evaluate_ablation_eligibility(req: AblationEligibilityRequest):
    return _execute_rule_eval("cc.eligibility.exclusions", req.dict(), req.patient_id)

# 10. Special population — pregnancy
@app.post("/api/v1/rules/cc.special.pregnancy", tags=["15 Individual Guideline Rules"])
def evaluate_pregnancy_rule(req: PregnancyRequest):
    return _execute_rule_eval("cc.special.pregnancy", req.dict(), req.patient_id)

# 11. Special population — postpartum
@app.post("/api/v1/rules/cc.special.postpartum", tags=["15 Individual Guideline Rules"])
def evaluate_postpartum_rule(req: PostpartumRequest):
    return _execute_rule_eval("cc.special.postpartum", req.dict(), req.patient_id)

# 12. Special population — total hysterectomy
@app.post("/api/v1/rules/cc.special.total_hysterectomy", tags=["15 Individual Guideline Rules"])
def evaluate_hysterectomy_rule(req: HysterectomyRequest):
    return _execute_rule_eval("cc.special.total_hysterectomy", req.dict(), req.patient_id)

# 13. Special population — HPV vaccinated
@app.post("/api/v1/rules/cc.special.hpv_vaccinated", tags=["15 Individual Guideline Rules"])
def evaluate_hpv_vaccinated(req: HpvVaccinatedRequest):
    return _execute_rule_eval("cc.special.hpv_vaccinated", req.dict(), req.patient_id)

# 14. Special population — postmenopausal
@app.post("/api/v1/rules/cc.special.postmenopausal", tags=["15 Individual Guideline Rules"])
def evaluate_postmenopausal(req: PostmenopausalRequest):
    return _execute_rule_eval("cc.special.postmenopausal", req.dict(), req.patient_id)

# 15. Special population — age 65+
@app.post("/api/v1/rules/cc.special.age_65_plus", tags=["15 Individual Guideline Rules"])
def evaluate_age_65_plus(req: Age65PlusRequest):
    return _execute_rule_eval("cc.special.age_65_plus", req.dict(), req.patient_id)