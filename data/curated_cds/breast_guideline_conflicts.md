# Breast cancer CDS — recorded guideline conflicts and resolutions

Source of truth: **Kenya National Cancer Screening & Early Diagnosis Guidelines, 2nd Edition (2024)** — breast chapter (`kenya_ncsedg_2024_breast`).

The 2024 guideline contains a small number of internal tensions and points where a
naïve reading could produce an unsafe or over-eager recommendation. Each is resolved
below and the resolution is encoded in the deterministic rules in
`packages/curated_cds/__init__.py`. These policies are clinical-authority decisions, not
LLM output; the LLM never overrides them.

## 1. Average-risk clinical breast exam interval, ages 25–34
**Conflict.** Narrative text and Table 9 differ on the CBE interval for average-risk
women aged 25–34 (a 2-yearly figure appears in one place, 3-yearly in Table 9).
**Resolution.** Use **CBE every 3 years** for average-risk 25–34 (Table 9 is treated as
the operative schedule). Encoded in `_BREAST_AGE_BANDS` (band `cbe_3y`, interval 3 years).
Ages 35–39 remain CBE + ultrasound 2-yearly; 40–55 CBE + mammography annually; 56–74
CBE + mammography 2-yearly; <25 breast awareness only; 75+ shared decision.

## 2. Male breast-cancer genetics-referral threshold
**Conflict.** The genetics-referral criteria are written for female probands; the
threshold for a male breast-cancer case in the family is ambiguous.
**Resolution.** A family history of **male breast cancer qualifies for genetic-counselling
referral when the affected male was ≤65 at diagnosis, OR at any age when it is a close
(first-/second-degree) family member.** Encoded in `derive_breast_genetics_referral`
(`MALE_BREAST_CANCER` criterion: `male_age <= 65` OR `close_family_history == yes`).

## 3. BI-RADS 1–2 after a diagnostic/recall episode
**Conflict.** Diagnostic-imaging guidance could be read as recommending annual imaging
after any imaging episode, which would override the patient's risk-based routine interval.
**Resolution.** **BI-RADS 1 (negative) and 2 (benign) resume the patient's risk-based
screening interval; they do NOT force an annual schedule.** Only BI-RADS 0 (incomplete →
additional imaging), 4 and 5 (biopsy) and 3 (short-interval follow-up) drive their own
actions. Encoded in `map_bc_mammography_birads`.

## 4. Hormonal / reproductive / lifestyle factors
**Conflict.** The guideline lists hormonal, reproductive and lifestyle factors (HRT, early
menarche, late menopause, nulliparity, alcohol, obesity, physical inactivity) as breast-
cancer risk factors, which could be misread as auto-classifying a woman as "high risk".
**Resolution.** These factors are **counselling-only and are never used to auto-classify a
woman into the high-risk screening pathway.** High-risk classification uses only the five
defined characteristics (strong family history, prior high-risk biopsy, chest-wall
radiation, previous breast cancer, known pathogenic mutation). Hormonal/lifestyle inputs
are captured for counselling and surface as advice, not as a pathway change. Encoded by
their exclusion from `_BREAST_HIGH_RISK_FIELDS`.

## 5. Known pathogenic mutation carrier
**Conflict.** For a woman with a known BRCA1/BRCA2 (or other high-penetrance) mutation, the
guideline expects intensified surveillance but does not specify an exact imaging schedule
suitable for auto-generation at this level of care.
**Resolution.** A **known pathogenic mutation routes to specialist/high-risk review; the
system does NOT invent a specific imaging schedule.** The rule classifies the patient as
high-risk and opens the high-risk breast-screening-plan form for a specialist-set interval,
rather than emitting an average-risk schedule. Encoded in
`map_bc_screening_high_risk_known_mutation` and the high-risk plan form.

---

### Cross-cutting safety policies (also enforced in code)
- **Unknown is never "no".** Any high-risk characteristic left unknown yields
  `unknown_missing_information`, never `average_risk`. The average-risk schedule is withheld
  until the risk fields are explicitly completed.
- **Pending / not-done imaging or pathology emits no treatment referral** — BI-RADS and
  histopathology rules return a silent recommendation when the result is pending/not_done.
- **Symptomatic / abnormal CBE** takes precedence over any routine screening schedule.
- **No side effect on evaluation.** Referrals, appointments and forms are created only when
  a clinician selects "Accept & act"; identical inputs reuse the same fingerprint and never
  create a duplicate.
