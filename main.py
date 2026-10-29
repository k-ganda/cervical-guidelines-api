"""
Kenya Cervical and Breast Cancer Guideline Rules API
Includes 15 Cervical Cancer rules and 11 Breast Cancer rules (26 total).
"""
from enum import Enum
from typing import Optional, get_args
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Import Dr. Fred's curated CDS package
from packages import curated_cds

# =====================================================================
# DATA DICTIONARY ALIGNMENT
# =====================================================================
# Requests speak the data dictionary: a field is sent under the label the app's form
# carries ("HIV Status"), and answered with the wording the form offers ("Negative").
# The rule logic below still works in the short names and codes it was written with, so
# both are translated here, at the edge, and nowhere else.

FIELD_LABELS = {
    "hpv_result": "HPV Test Findings",
    "latest_hpv_result": "HPV Test Findings",
    "hr_hpv_triage_result": "HPV Test Findings",
    "hiv_status": "HIV Status",
    "sample_date": "Sample Date",
    "result_date": "Result Date",
    "cytology_result": "Pap Smear",
    "via_result": "VIA or VIA/VILI",
    "via_exam_date": "VIA exam date",
    "colposcopy_result": "Colposcopy result",
    "colposcopy_date": "Colposcopy date",
    "biopsy_done": "Biopsy done",
    "biopsy_kit_available": "Biopsy kit available",
    "biopsy_result": "Biopsy / histology result",
    "hpv_vaccination_status": "HPV Vaccination Status",
    "pregnancy_status": "Pregnancy Status",
    "gestational_age_weeks": "Gestational age",
    "postpartum_weeks_since_delivery": "Weeks since Delivery",
    "precancer_treatment_indicated": "Precancer treatment indicated",
    "history_total_hysterectomy": "Hysterectomy",
    "history_treatment_precancer_or_cancer": "Prior treatment of cancer/precancer",
    "known_allergy_to_acetic_acid": "Allergy to acetic acid",
    "age_years": "Client Age",
    "date_of_birth": "Date of birth",
    "breast_previous_abnormal_biopsy": "Previous Abnormal Biopsy",
    "breast_previous_chest_wall_radiation": "Chest Wall Radiation",
    "mammography_birads": "Mammogram – BI-RADS",
    "ablation_c1_positive_screen_or_eligible_precancer": "Ablation criterion 1: Positive screen or eligible precancer",
    "ablation_c2_entire_lesion_and_margins_visible": "Ablation criterion 2: Entire lesion and margins visible",
    "ablation_c3_lesion_lte_75_percent": "Ablation criterion 3: Lesion covers 75% of the cervix or less",
    "ablation_c4_no_canal_gt2mm_or_vaginal_extension": "Ablation criterion 4: No extension >2 mm into canal or onto vagina",
    "ablation_c5_probe_full_coverage_no_gap_gt2mm": "Ablation criterion 5: Probe covers the lesion fully, no gap >2 mm",
    "ablation_c6_no_suspicion_invasive_cancer": "Ablation criterion 6: No suspicion of invasive cancer",
    "ablation_c7_no_active_pid_cervicitis_or_polyp": "Ablation criterion 7: No active PID, cervicitis or polyp",
    "ablation_c8_not_pregnant_and_postpartum_6w_or_more": "Ablation criterion 8: Not pregnant and 6+ weeks postpartum",
    "ablation_c9_no_prior_precancer_treatment": "Ablation criterion 9: No prior precancer treatment",
    "ablation_c10_informed_consent_given": "Ablation criterion 10: Informed consent given",
}

# The answer as the form words it -> the code the rule logic matches on. Only the fields
# whose wording changed appear here; anything else is passed through untouched.
ANSWER_CODES = {
    "hpv_result": {"Negative": "negative", "Positive": "positive"},
    "latest_hpv_result": {"Negative": "negative", "Positive": "positive"},
    "hr_hpv_triage_result": {"Positive": "positive", "Negative": "negative"},
    "hiv_status": {"Positive": "positive", "Negative": "negative", "Unknown": "unknown"},
    "via_result": {"Negative": "VIA_NEGATIVE", "Positive": "VIA_POSITIVE",
                   "Suspicious for Cancer": "SUSPICIOUS_FOR_CANCER", "Unsatisfactory": "INADEQUATE_UNSATISFACTORY"},
    "colposcopy_result": {"Negative": "COLPOSCOPY_NEGATIVE", "Positive": "COLPOSCOPY_POSITIVE",
                          "Suspicious for Cancer": "SUSPICIOUS_FOR_CANCER", "Inadequate colposcopy": "INADEQUATE_COLPOSCOPY"},
    "cytology_result": {
        "NILM(Normal)": "NILM",
        "ASCUS(Atypical squamous cells of undetermined significance)": "ASC_US",
        "LSIL (Low-grade squamous intraepithelial lesion)": "LSIL",
        "HSIL/CIS(High grade squamous intraepithelial lesion/Carcinoma in situ)": "HSIL",
        "AGC (Atypical glandular cells of undetermined significance)": "AGC",
        "Squamous Cell Carcinoma": "SQUAMOUS_CELL_CARCINOMA",
        "Adenocarcinoma": "ADENOCARCINOMA",
        "Other Malignant Neoplasm": "OTHER_MALIGNANT_NEOPLASM",
        "Unsatisfactory": "UNSATISFACTORY",
    },
    "hpv_vaccination_status": {"Fully Vaccinated against HPV": "vaccinated", "Partially Vaccinated": "partially_vaccinated"},
    "pregnancy_status": {"Currently Pregnant": "pregnant"},
    "mammography_birads": {"BI-RADS 0": "BI_RADS_0", "BI-RADS 1": "BI_RADS_1", "BI-RADS 2": "BI_RADS_2",
                           "BI-RADS 3": "BI_RADS_3", "BI-RADS 4": "BI_RADS_4", "BI-RADS 5": "BI_RADS_5"},
}


# The card reports what it reasoned over. It is read next to the request that produced it,
# so it answers in the same words: the label the field was sent under, and the wording the
# form offers. The short names and codes stay inside the rule logic.
_LABEL_BY_FACT = dict(FIELD_LABELS, **{
    "hpv_sample_collection_date": "Sample Date",
    "hpv_result_available_date": "Result Date",
    "hpv_test_date": "Sample Date",
})
_ANSWER_BY_CODE = {field: {code: answer for answer, code in options.items()}
                   for field, options in ANSWER_CODES.items()}


def _in_dictionary_terms(facts_used):
    """Facts as the data dictionary words them. Derived values a rule computes for itself -
    an ablation eligibility, a risk classification - have no dictionary entry and are left
    exactly as the rule reported them."""
    if not isinstance(facts_used, dict):
        return facts_used
    def worded(fact, value):
        # a derived value may be a list (the ablation criteria that failed) - leave it be
        return _ANSWER_BY_CODE.get(fact, {}).get(value, value) if isinstance(value, str) else value

    return {_LABEL_BY_FACT.get(fact, fact): worded(fact, value) for fact, value in facts_used.items()}


def _answer_code(field: str, value):
    """The code the rule logic expects, from whatever casing the answer arrived in.

    Capitalisation must never decide whether a woman gets advice: "negative" typed by an
    older record means the same as the form's "Negative".
    """
    options = ANSWER_CODES.get(field)
    if not options or not isinstance(value, str):
        return value
    for answer, code in options.items():
        if answer.casefold() == value.strip().casefold():
            return code
    return value


class RuleRequest(BaseModel):
    """Every rule request: fields are named as the data dictionary labels them.

    Unknown field names are rejected rather than ignored. A request that still used the
    old short names would otherwise be answered from the schema defaults - a card that
    looks right and was computed from data nobody sent.
    """

    model_config = ConfigDict(alias_generator=lambda name: FIELD_LABELS.get(name, name),
                              extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _accept_any_casing(cls, data):
        """An answer is matched however it was capitalised: a record holding "negative"
        means what the form calls "Negative"."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for name, field in cls.model_fields.items():
            choices = next((a for a in (field.annotation, *get_args(field.annotation))
                            if isinstance(a, type) and issubclass(a, Enum)), None)
            key = field.alias if field.alias in out else (name if name in out else None)
            if choices is None or key is None or not isinstance(out[key], str):
                continue
            answer = out[key].strip().casefold()
            match = next((c.value for c in choices if c.value.casefold() == answer), None)
            if match is not None:
                out[key] = match
        return out

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
    negative = "Negative"
    positive = "Positive"
    invalid_or_unsatisfactory = "invalid_or_unsatisfactory"

class HivStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    positive = "Positive"
    negative = "Negative"
    unknown = "Unknown"
    not_disclosed = "not_disclosed"

class ViaResultEnum(str, Enum):
    not_recorded = "not_recorded"
    via_negative = "Negative"
    via_positive = "Positive"
    suspicious = "Suspicious for Cancer"
    inadequate = "Unsatisfactory"

class CytologyResultEnum(str, Enum):
    not_recorded = "not_recorded"
    nilm = "NILM(Normal)"
    ascus = "ASCUS(Atypical squamous cells of undetermined significance)"
    lsil = "LSIL (Low-grade squamous intraepithelial lesion)"
    asc_h = "ASC_H"
    hsil = "HSIL/CIS(High grade squamous intraepithelial lesion/Carcinoma in situ)"
    agc = "AGC (Atypical glandular cells of undetermined significance)"
    ais = "AIS"
    squamous_cell_carcinoma = "Squamous Cell Carcinoma"
    adenocarcinoma = "Adenocarcinoma"
    other_malignant_neoplasm = "Other Malignant Neoplasm"
    unsatisfactory = "Unsatisfactory"

class ColposcopyResultEnum(str, Enum):
    not_recorded = "not_recorded"
    negative = "Negative"
    positive = "Positive"
    suspicious = "Suspicious for Cancer"
    inadequate = "Inadequate colposcopy"

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
    pregnant = "Currently Pregnant"
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
    vaccinated = "Fully Vaccinated against HPV"
    partially_vaccinated = "Partially Vaccinated"
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
    positive = "Positive"
    negative = "Negative"
    not_applicable = "not_applicable"

class BreastBiopsyFindingEnum(str, Enum):
    not_recorded = "not_recorded"
    atypical_hyperplasia = "atypical_hyperplasia"
    lobular_carcinoma_in_situ = "lobular_carcinoma_in_situ"
    other_benign = "other_benign"


class BreastLateralityEnum(str, Enum):
    not_recorded = "not_recorded"
    left = "left"
    right = "right"
    bilateral = "bilateral"


class BiradsEnum(str, Enum):
    not_recorded = "not_recorded"
    pending = "PENDING"
    not_done = "NOT_DONE"
    birads_0 = "BI-RADS 0"
    birads_1 = "BI-RADS 1"
    birads_2 = "BI-RADS 2"
    birads_3 = "BI-RADS 3"
    birads_4 = "BI-RADS 4"
    birads_5 = "BI-RADS 5"


class BreastHistopathologyEnum(str, Enum):
    not_recorded = "not_recorded"
    pending = "pending"
    not_done = "not_done"
    negative_for_malignancy = "negative_for_malignancy"
    indeterminate = "indeterminate"
    inadequate = "inadequate"
    malignant = "malignant"


class ReceptorStatusEnum(str, Enum):
    not_recorded = "not_recorded"
    positive = "positive"
    negative = "negative"


# REQUEST SCHEMAS


# ---------------- CERVICAL CANCER SCHEMAS (15 RULES) ----------------

class HpvInterpretationRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    hpv_result: HpvResultEnum = Field(HpvResultEnum.negative, description="PRIMARY: Select HPV Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.positive, description="DEPENDENT: Select HIV Status")
    sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Collection Date (YYYY-MM-DD)")
    result_date: Optional[str] = Field("2026-08-20", description="DEPENDENT: Result Available Date (YYYY-MM-DD)")

class ViaEligibilityRequest(RuleRequest):
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

class ViaInterpretationRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    via_result: ViaResultEnum = Field(ViaResultEnum.via_negative, description="PRIMARY: Select VIA Result")
    hiv_status: HivStatusEnum = Field(HivStatusEnum.negative, description="DEPENDENT: Select HIV Status")
    via_exam_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: VIA Exam Date (YYYY-MM-DD)")

class CytologyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    cytology_result: CytologyResultEnum = Field(CytologyResultEnum.nilm, description="PRIMARY: Select Cytology Result")
    hr_hpv_triage_result: HrHpvTriageResultEnum = Field(HrHpvTriageResultEnum.not_recorded, description="DEPENDENT: HR-HPV Triage Result")
    cytology_sample_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Sample Date (YYYY-MM-DD)")

class ColposcopyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    colposcopy_result: ColposcopyResultEnum = Field(ColposcopyResultEnum.negative, description="PRIMARY: Select Colposcopy Result")
    biopsy_kit_available: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Biopsy Kit Available")
    biopsy_done: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Biopsy Done")
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.not_recorded, description="DEPENDENT: Biopsy Result")
    colposcopy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Colposcopy Date (YYYY-MM-DD)")

class ColposcopySurveillanceRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

class PersistentHpvRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    prior_negative_colposcopy_date: str = Field("2024-08-11", description="PRIMARY: Date of Negative Colposcopy (YYYY-MM-DD)")
    latest_hpv_result: HpvResultEnum = Field(HpvResultEnum.positive, description="DEPENDENT: Latest HPV Result")
    facility_provides_colposcopy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Facility Provides Colposcopy")

class HistologyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    biopsy_result: BiopsyResultEnum = Field(BiopsyResultEnum.cin2, description="PRIMARY: Select Biopsy Result")
    biopsy_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Biopsy Date (YYYY-MM-DD)")

class AblationEligibilityRequest(RuleRequest):
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

class PregnancyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    pregnancy_status: PregnancyStatusEnum = Field(PregnancyStatusEnum.pregnant, description="PRIMARY: Select Pregnancy Status")
    gestational_age_weeks: Optional[int] = Field(10, description="DEPENDENT: Gestational Age in Weeks")
    mass_suspicious_for_invasive_disease: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Suspicious Cervical Mass")
    precancer_treatment_indicated: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Precancer Treatment Indicated")
    date_of_delivery: Optional[str] = Field(None, description="DEPENDENT: Expected Delivery Date (YYYY-MM-DD)")

class PostpartumRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    postpartum_status: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Postpartum Status")
    postpartum_weeks_since_delivery: int = Field(4, description="DEPENDENT: Weeks Postpartum")
    date_of_delivery: Optional[str] = Field("2026-07-14", description="DEPENDENT: Date of Delivery (YYYY-MM-DD)")

class HysterectomyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    history_total_hysterectomy: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Total Hysterectomy?")
    hysterectomy_indication: HysterectomyIndicationEnum = Field(HysterectomyIndicationEnum.benign, description="DEPENDENT: Indication")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")

class HpvVaccinatedRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    hpv_vaccination_status: VaccinationStatusEnum = Field(VaccinationStatusEnum.vaccinated, description="PRIMARY: HPV Vaccination Status")

class PostmenopausalRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    menopausal_status: MenopausalStatusEnum = Field(MenopausalStatusEnum.postmenopausal, description="PRIMARY: Menopausal Status")
    age_years: Optional[int] = Field(55, description="DEPENDENT: Age in Years")
    screening_method: ScreeningMethodEnum = Field(ScreeningMethodEnum.hpv, description="DEPENDENT: Screening Method")
    cytology_sample_date: Optional[str] = Field(None, description="DEPENDENT: Cytology Sample Date (YYYY-MM-DD)")
    hpv_sample_collection_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: HPV Sample Date (YYYY-MM-DD)")

class Age65PlusRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    age_years: int = Field(68, description="PRIMARY: Patient Age (>=65)")
    history_high_grade_cin_or_cervical_cancer: YesNoEnum = Field(YesNoEnum.no, description="DEPENDENT: Prior High-Grade CIN/Cancer")
    negative_hpv_tests_last_10_years: Optional[int] = Field(2, description="DEPENDENT: Negative HPV Tests Last 10 Yrs")
    negative_pap_tests_last_10_years: Optional[int] = Field(0, description="DEPENDENT: Negative Pap Tests Last 10 Yrs")
    screening_history_complete_for_age65_exit_assessment: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Screening History Complete")


# ---------------- BREAST CANCER SCHEMAS (11 RULES) ----------------

class BreastRiskClassificationRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_first_degree_relative_affected: YesNoEnum = Field(YesNoEnum.no, description="First-degree relative with breast cancer")
    breast_previous_abnormal_biopsy: YesNoEnum = Field(YesNoEnum.no, description="Previous abnormal breast biopsy")
    breast_previous_chest_wall_radiation: YesNoEnum = Field(YesNoEnum.no, description="Previous chest wall radiation before age 30")
    breast_previous_cancer: YesNoEnum = Field(YesNoEnum.no, description="Personal history of breast cancer")
    breast_known_pathogenic_mutation: YesNoEnum = Field(YesNoEnum.no, description="Known BRCA1/BRCA2 or other mutation")
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.normal, description="Clinical Breast Exam Result")

class BreastAverageRiskScreeningRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    date_of_birth: Optional[str] = Field("1982-05-15", description="Patient Date of Birth (YYYY-MM-DD)")
    age_years: Optional[int] = Field(44, description="Patient Age in Years")
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.normal, description="Clinical Breast Exam Result")
    breast_screening_shared_decision: BreastSharedDecisionEnum = Field(BreastSharedDecisionEnum.not_recorded, description="Shared Decision for Age 75+")


class BreastHighRiskFamilyHistoryRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_first_degree_relative_affected: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: First-degree relative with breast cancer")
    breast_first_degree_relatives_count: Optional[int] = Field(1, description="DEPENDENT: Affected first-degree relatives (rule covers 1-2)")
    breast_youngest_family_case_age: Optional[int] = Field(40, description="DEPENDENT: Age of youngest affected family case (start age = age-10, clamped 25-40)")
    date_of_birth: Optional[str] = Field(None, description="DEPENDENT: Date of Birth (YYYY-MM-DD)")
    age_years: Optional[int] = Field(35, description="DEPENDENT: Patient Age in Years")
    last_mammography_date: Optional[str] = Field(None, description="DEPENDENT: Last Mammography Date (YYYY-MM-DD)")
    breast_family_breast_ovarian_cases_count: Optional[int] = Field(None, description="DEPENDENT: Family breast/ovarian cases (genetics gate)")
    breast_family_generations_affected_count: Optional[int] = Field(None, description="DEPENDENT: Generations affected (genetics gate)")
    breast_family_any_onset_under_50: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Any family onset under 50 (genetics gate)")
    breast_confirmed_brca1_brca2_in_family: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Confirmed BRCA1/2 in family (genetics gate)")

class BreastHighRiskAbnormalBiopsyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_previous_abnormal_biopsy: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Previous abnormal breast biopsy")
    breast_previous_biopsy_finding: BreastBiopsyFindingEnum = Field(BreastBiopsyFindingEnum.atypical_hyperplasia, description="DEPENDENT: Biopsy finding")
    breast_invasive_carcinoma_ruled_out_after_biopsy: YesNoEnum = Field(YesNoEnum.yes, description="DEPENDENT: Invasive carcinoma ruled out")
    breast_high_risk_cbe_interval_months: Optional[int] = Field(12, description="DEPENDENT: CBE interval in months (6 or 12)")
    breast_previous_biopsy_date: Optional[str] = Field(None, description="DEPENDENT: Previous Biopsy Date (YYYY-MM-DD)")
    last_mammography_date: Optional[str] = Field(None, description="DEPENDENT: Last Mammography Date (YYYY-MM-DD)")

class BreastHighRiskChestRadiationRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_previous_chest_wall_radiation: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Chest wall radiation before age 30")
    breast_age_at_chest_radiation: Optional[int] = Field(20, description="DEPENDENT: Age at chest-wall radiation")
    breast_chest_radiation_date: Optional[str] = Field(None, description="DEPENDENT: Date of chest-wall radiation (YYYY-MM-DD)")
    date_of_birth: Optional[str] = Field(None, description="DEPENDENT: Date of Birth (YYYY-MM-DD)")
    age_years: Optional[int] = Field(33, description="DEPENDENT: Patient Age in Years")
    last_mammography_date: Optional[str] = Field(None, description="DEPENDENT: Last Mammography Date (YYYY-MM-DD)")

class BreastHighRiskPreviousCancerRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_previous_cancer: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Personal history of breast cancer")
    breast_previous_cancer_laterality: BreastLateralityEnum = Field(BreastLateralityEnum.left, description="DEPENDENT: Laterality of previous cancer")
    breast_high_risk_cbe_interval_months: Optional[int] = Field(12, description="DEPENDENT: CBE interval in months (6 or 12)")
    last_mammography_date: Optional[str] = Field(None, description="DEPENDENT: Last Mammography Date (YYYY-MM-DD)")
    breast_specialist_screening_plan: Optional[str] = Field(None, description="DEPENDENT: Documented specialist plan (bilateral cases)")

class BreastHighRiskKnownMutationRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_known_pathogenic_mutation: YesNoEnum = Field(YesNoEnum.yes, description="PRIMARY: Known pathogenic mutation")
    breast_pathogenic_mutation_type: Optional[str] = Field("BRCA1", description="DEPENDENT: Mutation type")
    breast_specialist_screening_plan: Optional[str] = Field(None, description="DEPENDENT: Recorded specialist screening plan")
    breast_specialist_screening_interval_months: Optional[int] = Field(None, description="DEPENDENT: Specialist screening interval (months)")
    breast_specialist_screening_modalities: Optional[str] = Field(None, description="DEPENDENT: Specialist screening modalities")
    breast_specialist_plan_date: Optional[str] = Field(None, description="DEPENDENT: Specialist plan date (YYYY-MM-DD)")
    last_mammography_date: Optional[str] = Field(None, description="DEPENDENT: Last Mammography Date (YYYY-MM-DD)")

class BreastGeneticsReferralRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_family_breast_ovarian_cases_count: Optional[int] = Field(3, description="Family breast/ovarian cases (>=3 with 2 generations + one <50)")
    breast_family_generations_affected_count: Optional[int] = Field(2, description="Generations affected")
    breast_family_any_onset_under_50: YesNoEnum = Field(YesNoEnum.yes, description="Any family onset under age 50")
    breast_bilateral_primary_cancer: YesNoEnum = Field(YesNoEnum.not_recorded, description="Bilateral primary breast cancer")
    breast_previous_cancer: YesNoEnum = Field(YesNoEnum.not_recorded, description="Personal history of breast cancer")
    breast_previous_cancer_diagnosis_age: Optional[int] = Field(None, description="Age at breast cancer diagnosis (<=35 qualifies)")
    breast_triple_negative_cancer: YesNoEnum = Field(YesNoEnum.not_recorded, description="Triple-negative breast cancer (<=60 qualifies)")
    breast_er_status: ReceptorStatusEnum = Field(ReceptorStatusEnum.not_recorded, description="ER status")
    breast_pr_status: ReceptorStatusEnum = Field(ReceptorStatusEnum.not_recorded, description="PR status")
    breast_her2_status: ReceptorStatusEnum = Field(ReceptorStatusEnum.not_recorded, description="HER2 status")
    breast_primary_ovarian_cancer_history: YesNoEnum = Field(YesNoEnum.not_recorded, description="Breast and ovarian cancer in same individual")
    breast_family_male_breast_cancer: YesNoEnum = Field(YesNoEnum.not_recorded, description="Male breast cancer in family")
    breast_family_male_case_age: Optional[int] = Field(None, description="Age of male breast cancer case (<=65 qualifies)")
    breast_family_male_case_close_family_history: YesNoEnum = Field(YesNoEnum.not_recorded, description="Male case is a close relative")
    breast_confirmed_brca1_brca2_in_family: YesNoEnum = Field(YesNoEnum.not_recorded, description="Confirmed BRCA1/BRCA2 in family")

class BreastCbeAbnormalRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.abnormal, description="PRIMARY: Clinical Breast Exam Result")
    breast_cbe_laterality: BreastLateralityEnum = Field(BreastLateralityEnum.not_recorded, description="DEPENDENT: CBE laterality")
    breast_cbe_lump: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Lump")
    breast_cbe_pain: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Pain")
    breast_cbe_nipple_discharge: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Nipple discharge")
    breast_cbe_skin_changes: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Skin changes")
    breast_cbe_axillary_nodes: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Axillary nodes")
    breast_symptomatic_or_abnormal: YesNoEnum = Field(YesNoEnum.not_recorded, description="DEPENDENT: Symptomatic or abnormal")

class BreastMammographyBiradsRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    mammography_birads: BiradsEnum = Field(BiradsEnum.birads_3, description="PRIMARY: BI-RADS category")
    mammography_date: Optional[str] = Field("2026-08-11", description="DEPENDENT: Mammography Date (YYYY-MM-DD) - scheduling base date")
    date_of_birth: Optional[str] = Field(None, description="DEPENDENT: Date of Birth (YYYY-MM-DD)")
    age_years: Optional[int] = Field(45, description="DEPENDENT: Patient Age in Years (BI-RADS 1/2 interval)")
    breast_cbe_result: BreastCbeResultEnum = Field(BreastCbeResultEnum.not_recorded, description="DEPENDENT: CBE result")
    breast_screening_shared_decision: BreastSharedDecisionEnum = Field(BreastSharedDecisionEnum.not_recorded, description="DEPENDENT: Shared decision for age 75+")

class BreastHistopathologyRequest(RuleRequest):
    patient_id: str = "demo-patient-001"
    breast_histopathology_result: BreastHistopathologyEnum = Field(BreastHistopathologyEnum.malignant, description="PRIMARY: Breast histopathology result")


# CORE EVALUATION HELPERS


_NUMERIC_FACTS = {
    # cervical
    "gestational_age_weeks", "postpartum_weeks_since_delivery", "age_years",
    "negative_hpv_tests_last_10_years", "negative_pap_tests_last_10_years",
    # breast
    "breast_first_degree_relatives_count", "breast_youngest_family_case_age",
    "breast_high_risk_cbe_interval_months", "breast_age_at_chest_radiation",
    "breast_previous_cancer_diagnosis_age", "breast_family_breast_ovarian_cases_count",
    "breast_family_generations_affected_count", "breast_family_male_case_age",
    "breast_specialist_screening_interval_months",
}


def _execute_rule_eval(rule_id: str, raw_facts: dict, patient_id: str):
    """Shared evaluator for every curated rule, cervical and breast alike."""
    facts = {}

    # Clean inputs, cast numeric types, and translate the form's answers to rule codes
    for k, v in raw_facts.items():
        if v is not None and str(v) not in ("not_recorded", "string", ""):
            val = v.value if hasattr(v, "value") else v
            if k in _NUMERIC_FACTS:
                try:
                    facts[k] = int(val)
                except (ValueError, TypeError):
                    facts[k] = val
            else:
                facts[k] = _answer_code(k, str(val))

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
                "facts_used": _in_dictionary_terms(card.get("facts_used", facts)),
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
        "facts_evaluated": _in_dictionary_terms(facts)
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
    return _execute_rule_eval("cc.hpv.interpretation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.via.eligibility", tags=["15 Cervical Cancer Rules"])
def evaluate_via_eligibility(req: ViaEligibilityRequest):
    return _execute_rule_eval("cc.via.eligibility", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.via.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_via_rule(req: ViaInterpretationRequest):
    return _execute_rule_eval("cc.via.interpretation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.cytology.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_cytology_rule(req: CytologyRequest):
    return _execute_rule_eval("cc.cytology.interpretation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.colposcopy.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_colposcopy_rule(req: ColposcopyRequest):
    return _execute_rule_eval("cc.colposcopy.interpretation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.colposcopy.negative_surveillance", tags=["15 Cervical Cancer Rules"])
def evaluate_colposcopy_surveillance(req: ColposcopySurveillanceRequest):
    return _execute_rule_eval("cc.colposcopy.negative_surveillance", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.hpv.persistent_after_negative_colposcopy", tags=["15 Cervical Cancer Rules"])
def evaluate_persistent_hpv(req: PersistentHpvRequest):
    return _execute_rule_eval("cc.hpv.persistent_after_negative_colposcopy", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.histology.interpretation", tags=["15 Cervical Cancer Rules"])
def evaluate_histology_rule(req: HistologyRequest):
    return _execute_rule_eval("cc.histology.interpretation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.eligibility.exclusions", tags=["15 Cervical Cancer Rules"])
def evaluate_ablation_eligibility(req: AblationEligibilityRequest):
    return _execute_rule_eval("cc.eligibility.exclusions", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.pregnancy", tags=["15 Cervical Cancer Rules"])
def evaluate_pregnancy_rule(req: PregnancyRequest):
    return _execute_rule_eval("cc.special.pregnancy", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.postpartum", tags=["15 Cervical Cancer Rules"])
def evaluate_postpartum_rule(req: PostpartumRequest):
    return _execute_rule_eval("cc.special.postpartum", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.total_hysterectomy", tags=["15 Cervical Cancer Rules"])
def evaluate_hysterectomy_rule(req: HysterectomyRequest):
    return _execute_rule_eval("cc.special.total_hysterectomy", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.hpv_vaccinated", tags=["15 Cervical Cancer Rules"])
def evaluate_hpv_vaccinated(req: HpvVaccinatedRequest):
    return _execute_rule_eval("cc.special.hpv_vaccinated", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.postmenopausal", tags=["15 Cervical Cancer Rules"])
def evaluate_postmenopausal(req: PostmenopausalRequest):
    return _execute_rule_eval("cc.special.postmenopausal", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/cc.special.age_65_plus", tags=["15 Cervical Cancer Rules"])
def evaluate_age_65_plus(req: Age65PlusRequest):
    return _execute_rule_eval("cc.special.age_65_plus", req.model_dump(), req.patient_id)


# ---------------- 11 BREAST CANCER ENDPOINTS ----------------

@app.post("/api/v1/rules/bc.risk.classification", tags=["11 Breast Cancer Rules"])
def evaluate_breast_risk_classification(req: BreastRiskClassificationRequest):
    return _execute_rule_eval("bc.risk.classification", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.average_risk", tags=["11 Breast Cancer Rules"])
def evaluate_breast_average_risk_screening(req: BreastAverageRiskScreeningRequest):
    return _execute_rule_eval("bc.screening.average_risk", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.high_risk.family_history", tags=["11 Breast Cancer Rules"])
def evaluate_breast_high_risk_family_history(req: BreastHighRiskFamilyHistoryRequest):
    return _execute_rule_eval("bc.screening.high_risk.family_history", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.high_risk.abnormal_biopsy", tags=["11 Breast Cancer Rules"])
def evaluate_breast_high_risk_abnormal_biopsy(req: BreastHighRiskAbnormalBiopsyRequest):
    return _execute_rule_eval("bc.screening.high_risk.abnormal_biopsy", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.high_risk.chest_radiation", tags=["11 Breast Cancer Rules"])
def evaluate_breast_high_risk_chest_radiation(req: BreastHighRiskChestRadiationRequest):
    return _execute_rule_eval("bc.screening.high_risk.chest_radiation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.high_risk.previous_breast_cancer", tags=["11 Breast Cancer Rules"])
def evaluate_breast_high_risk_previous_cancer(req: BreastHighRiskPreviousCancerRequest):
    return _execute_rule_eval("bc.screening.high_risk.previous_breast_cancer", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.screening.high_risk.known_mutation", tags=["11 Breast Cancer Rules"])
def evaluate_breast_high_risk_known_mutation(req: BreastHighRiskKnownMutationRequest):
    return _execute_rule_eval("bc.screening.high_risk.known_mutation", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.genetics.referral", tags=["11 Breast Cancer Rules"])
def evaluate_breast_genetics_referral(req: BreastGeneticsReferralRequest):
    return _execute_rule_eval("bc.genetics.referral", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.cbe.abnormal", tags=["11 Breast Cancer Rules"])
def evaluate_breast_cbe_abnormal(req: BreastCbeAbnormalRequest):
    return _execute_rule_eval("bc.cbe.abnormal", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.mammography.birads", tags=["11 Breast Cancer Rules"])
def evaluate_breast_mammography_birads(req: BreastMammographyBiradsRequest):
    return _execute_rule_eval("bc.mammography.birads", req.model_dump(), req.patient_id)

@app.post("/api/v1/rules/bc.histopathology.interpretation", tags=["11 Breast Cancer Rules"])
def evaluate_breast_histopathology(req: BreastHistopathologyRequest):
    return _execute_rule_eval("bc.histopathology.interpretation", req.model_dump(), req.patient_id)
