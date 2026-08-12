# Skill: Clean and Prepare Kenya Cervical Cancer L2 DAK Artifacts for CDS Hooks

## Purpose

Use this skill to clean, relink, validate, and package the Kenya Cervical Cancer Level 2 Digital Adaptation Kit (L2 DAK) artifacts so that they are ready for downstream CDS Hooks implementation while preserving the WHO SMART Guidelines DAK structure.

The task is to improve the L2 JSON and XLSX artifact files inside the uploaded DAK ZIP, using:

1. The uploaded L2 DAK ZIP as the working artifact package.
2. The clinician-validated L1 recommendations workbook as the canonical recommendation source.
3. The original L1 recommendations workbook only as a comparison source to track what changed between the LLM-extracted L1 and clinician-validated L1 recommendations.
4. The previous L2 audit findings as the issue list and cleanup guide.

Do not use the original L1 workbook as a source of truth for final clinical linkage. It is used only to create provenance and change-tracking between LLM-generated recommendations and clinician-validated recommendations.

---

## Input files

Expected uploaded files:

```text
Kenya Cervical Cancer Template DAK.zip
l1_recommendations.xlsx
l1_recommendations_clinician_validated.xlsx
kenya_cervical_l2_audit.xlsx, if available from the previous step
```

If the audit workbook is not present, reconstruct the audit checks from the L2 files directly.

---

## Source-of-truth hierarchy

Use this hierarchy strictly:

| Priority | Source | Use |
|---:|---|---|
| 1 | `l1_recommendations_clinician_validated.xlsx` | Canonical validated L1 recommendation catalogue. All final L2 recommendation links must resolve here. |
| 2 | Existing L2 artifact JSON files in the DAK ZIP | Preserve structure and fields; correct links, logic, and redundancy. |
| 3 | Existing L2 artifact XLSX files in the DAK ZIP | Human-readable paired versions; regenerate from cleaned JSON while preserving sheet structure and formatting. |
| 4 | Previous L2 audit workbook | Issue list for orphan, misplaced, redundant, invalid, overused, or weak L2 elements. |
| 5 | `l1_recommendations.xlsx` | Comparison only. Use to track clinician edits compared with LLM-extracted L1 recommendations. Do not use as final canonical linkage. |
| 6 | Source guideline/PDF inside the DAK ZIP, if present | Use only to resolve unclear clinical wording or page references. |

Important rule: the final cleaned L2 package must use validated L1 IDs from `l1_recommendations_clinician_validated.xlsx`. Any L2 ID absent from the clinician-validated L1 workbook must be corrected, retired from CDS execution, or logged as unresolved.

---

## Main output

Produce a cleaned ZIP:

```text
Kenya_Cervical_Cancer_Template_DAK_cleaned_CDS_ready.zip
```

Also produce a summary workbook:

```text
Kenya_Cervical_Cancer_Template_DAK_cleanup_summary.xlsx
```

The cleaned ZIP must retain the original WHO SMART Guidelines DAK folder structure but with cleaned, renamed artifact files and new improvement logs.

---

## Required final ZIP structure

Use this folder and file naming pattern:

```text
Kenya Cervical Cancer Template DAK_cleaned/
  master_manifest.json
  source_index.json
  cross_artifact_validation.json
  cross_artifact_validation_cleaned.json
  improvement_master_log.json
  l1_clinician_change_tracking.json

  01_health_interventions/
    01_health_interventions_artifact.json
    01_health_interventions_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  02_personas/
    02_personas_artifact.json
    02_personas_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  03_user_scenarios/
    03_user_scenarios_artifact.json
    03_user_scenarios_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  04_workflows/
    04_workflows_artifact.json
    04_workflows_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  05_core_data_dictionary/
    05_core_data_dictionary_artifact.json
    05_core_data_dictionary_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  06_decision_support_scheduling/
    06_decision_support_scheduling_artifact.json
    06_decision_support_scheduling_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  07_indicators/
    07_indicators_artifact.json
    07_indicators_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json

  08_requirements/
    08_requirements_artifact.json
    08_requirements_artifact.xlsx
    extraction_log.json
    validation_report.json
    improvements_log.json
```

Remove temporary office lock files such as:

```text
.~lock.artifact.xlsx#
```

Do not include these in the cleaned ZIP.

---

## Key definitions

### Canonical L1 recommendation

A recommendation present in `l1_recommendations_clinician_validated.xlsx`.

### Original L1 recommendation

A recommendation present in `l1_recommendations.xlsx`. This is used only for comparison against the clinician-validated version.

### Orphan L2 element

An L2 element that has no valid link to a clinician-validated L1 recommendation or no valid internal traceability to another DAK element where linkage is required.

### Misplaced recommendation link

A recommendation linked to an L2 item whose purpose does not match the recommendation’s clinical meaning.

### Redundant L2 element

A duplicated or near-duplicated L2 item, including flowchart fragments that repeat consolidated decision rules.

### CDS-executable element

An L2 decision rule, scheduling rule, workflow trigger, or data element that is sufficiently structured to support CDS Hooks implementation.

### Metadata-only element

An item retained for documentation, traceability, programme monitoring, or provenance but not used as executable CDS logic.

---

## Required cleanup statuses

Every changed or reviewed item should receive one of these statuses when applicable:

| Status | Meaning |
|---|---|
| `validated` | L1 link exists in clinician-validated L1 and logic directly follows it. |
| `needs_clinical_review` | Logic appears clinically plausible but is not fully supported by validated L1 or has ambiguity. |
| `retired_from_cds` | Retained for provenance but excluded from executable CDS. |
| `metadata_only` | Useful for documentation or reporting but not for CDS execution. |
| `unresolved` | Cannot be safely corrected without manual review. |

Do not delete clinically relevant items outright unless they are pure duplicates with no independent provenance. Prefer retaining them with:

```json
{
  "cds_executable": false,
  "clinical_review_status": "retired_from_cds",
  "retirement_reason": "Duplicate flowchart fragment superseded by consolidated decision rule."
}
```

---

## Improvement log schema

Each DAK element folder must include a new `improvements_log.json`.

Use this schema consistently:

```json
{
  "artifact_folder": "04_workflows",
  "artifact_name": "Business Processes and Workflows",
  "source_artifact_json": "artifact.json",
  "cleaned_artifact_json": "04_workflows_artifact.json",
  "source_artifact_xlsx": "artifact.xlsx",
  "cleaned_artifact_xlsx": "04_workflows_artifact.xlsx",
  "l1_source_of_truth": "l1_recommendations_clinician_validated.xlsx",
  "l1_comparison_source": "l1_recommendations.xlsx",
  "improvement_run_date": "YYYY-MM-DD",
  "overall_change_summary": {
    "records_reviewed": 0,
    "records_updated": 0,
    "records_added": 0,
    "records_retired": 0,
    "recommendation_links_corrected": 0,
    "unresolved_items_remaining": 0,
    "clinical_review_required": 0
  },
  "changes": [
    {
      "change_id": "04_workflows.CHANGE.001",
      "sheet_or_section": "workflow_steps",
      "record_id": "CC.WF.04.STEP.003",
      "change_type": "relinked_l1_recommendation",
      "severity": "major",
      "before": {
        "linked_l1_recommendation_ids": ["KEN-CC-L1-invalid-or-legacy"]
      },
      "after": {
        "linked_l1_recommendation_ids": ["KEN-CC-L1-validated"]
      },
      "reason": "Original linked recommendation ID was absent from clinician-validated L1 catalogue and was replaced with the validated recommendation that matches the clinical logic.",
      "audit_basis": "L2 audit: missing or invalid L1 link",
      "clinical_basis": {
        "validated_l1_id": "KEN-CC-L1-validated",
        "validated_l1_text": "Validated recommendation text"
      },
      "original_l1_comparison": {
        "original_l1_id": "KEN-CC-L1-original-or-null",
        "original_l1_text": "Original LLM-extracted recommendation text, if matched",
        "clinician_change_type": "unchanged | wording_changed | split | merged | deleted | newly_added | id_changed | unknown"
      },
      "requires_clinical_review": false
    }
  ],
  "unresolved_items": [
    {
      "record_id": "CC.XYZ",
      "issue": "No validated L1 recommendation found",
      "recommended_next_action": "Review clinician-validated L1 workbook and source guideline manually"
    }
  ]
}
```

---

## Root-level improvement master log

Create `improvement_master_log.json` at the root of the cleaned package.

It should summarize changes across all DAK elements:

```json
{
  "package_name": "Kenya Cervical Cancer Template DAK",
  "cleanup_run_date": "YYYY-MM-DD",
  "canonical_l1_source": "l1_recommendations_clinician_validated.xlsx",
  "l1_comparison_source": "l1_recommendations.xlsx",
  "dak_elements_cleaned": 8,
  "total_records_reviewed": 0,
  "total_records_updated": 0,
  "total_records_added": 0,
  "total_records_retired_from_cds": 0,
  "total_recommendation_links_corrected": 0,
  "total_unresolved_items_remaining": 0,
  "total_items_needing_clinical_review": 0,
  "major_findings": [],
  "dak_element_logs": [
    {
      "dak_element": "04_workflows",
      "improvements_log": "04_workflows/improvements_log.json",
      "records_updated": 0,
      "records_retired": 0,
      "unresolved_items_remaining": 0
    }
  ]
}
```

---

## L1 clinician change-tracking log

Create a root-level file:

```text
l1_clinician_change_tracking.json
```

This file compares the original LLM-extracted L1 workbook with the clinician-validated L1 workbook. It is for provenance only and should not control final L2 links.

### Matching strategy

Match original L1 to clinician-validated L1 using:

1. Exact recommendation ID match.
2. Exact normalized recommendation text match.
3. High-similarity text match.
4. Manual mapping if obvious from title, section, source page, or clinical theme.

### Change categories

Use these categories:

| Change type | Meaning |
|---|---|
| `unchanged` | Same ID and same or near-identical text. |
| `wording_changed` | Same clinical meaning, clinician edited wording. |
| `id_changed` | Same recommendation, different ID. |
| `split` | One LLM recommendation became multiple clinician-validated recommendations. |
| `merged` | Multiple LLM recommendations became one clinician-validated recommendation. |
| `deleted` | LLM recommendation not retained by clinician validation. |
| `newly_added` | Clinician-validated recommendation has no clear original LLM equivalent. |
| `unknown` | Relationship cannot be safely determined. |

### File schema

```json
{
  "comparison_date": "YYYY-MM-DD",
  "original_l1_file": "l1_recommendations.xlsx",
  "clinician_validated_l1_file": "l1_recommendations_clinician_validated.xlsx",
  "summary": {
    "original_l1_count": 0,
    "clinician_validated_l1_count": 0,
    "unchanged": 0,
    "wording_changed": 0,
    "id_changed": 0,
    "split": 0,
    "merged": 0,
    "deleted": 0,
    "newly_added": 0,
    "unknown": 0
  },
  "mappings": [
    {
      "mapping_id": "L1MAP.001",
      "original_l1_ids": ["KEN-CC-L1-original"],
      "validated_l1_ids": ["KEN-CC-L1-validated"],
      "change_type": "wording_changed",
      "similarity_score": 0.94,
      "original_text": "Original LLM-extracted recommendation text",
      "validated_text": "Clinician-validated recommendation text",
      "notes": "Same clinical intent; clinician tightened wording."
    }
  ],
  "unmatched_original_l1": [],
  "unmatched_validated_l1": []
}
```

---

## Cross-cutting cleanup rules

### 1. Validate all final L1 links against clinician-validated L1

For every field named like:

```text
linked_l1_recommendation_ids
linked_recommendation_ids
source_recommendation_id
recommendation_id
canonical_l1_recommendation_ids
```

apply these rules:

| Condition | Action |
|---|---|
| ID exists in clinician-validated L1 | Keep it. |
| ID does not exist in clinician-validated L1 but maps clearly to a validated ID | Replace with validated ID and log the mapping. |
| ID exists only in original L1 | Treat as legacy; do not keep as final clinical link unless also present in clinician-validated L1. Store it in `legacy_l1_recommendation_ids` if useful. |
| ID does not exist in either L1 file | Mark unresolved and remove from CDS-executable logic unless clinically essential. |
| Multiple IDs are stored as one semicolon-separated string | Convert to a JSON array where possible. |
| ID is actually a data element, flowchart, rule, or workflow ID | Move it to the correct field. |
| ID is over-broad for the L2 element | Replace with narrower validated L1 IDs where possible. |

In XLSX outputs, semicolon-separated strings may be retained for readability and spreadsheet compatibility. In JSON outputs, use arrays wherever structurally appropriate.

Example JSON normalization:

Before:

```json
{
  "linked_recommendation_ids": "KEN-CC-L1-3b4850a337; KEN-CC-L1-e1bc4a5522"
}
```

After:

```json
{
  "linked_recommendation_ids": [
    "KEN-CC-L1-3b4850a337",
    "KEN-CC-L1-e1bc4a5522"
  ]
}
```

---

## Special rule for `KEN-CC-L1-aa03884194`

`KEN-CC-L1-aa03884194` is present in the clinician-validated L1 file and should be interpreted as a high-level recommendation about implementing a screen-triage-and-treat strategy for efficient management, ideally using a single-visit approach when practical.

Use it only for L2 elements that represent the overall screen-triage-treat strategy or single-visit approach.

Do not use it as a catch-all link for every HPV, VIA, cytology, treatment, referral, or follow-up rule.

Where possible, replace it with narrower validated L1 recommendations for:

| Logic area | Preferred validated L1 theme |
|---|---|
| HPV primary screening | HPV testing as primary screening method. |
| VIA fallback pathway | VIA when HPV is unavailable or risk of loss to follow-up is high. |
| Cytology pathway | Pap smear/cytology recommendation. |
| Suspected cancer | Immediate referral for evaluation, biopsy, and further management. |
| Ablation eligibility | Criteria for ablative treatment. |
| LEEP/excision | Excisional treatment recommendation. |
| Post-treatment follow-up | Twelve-month follow-up/retest recommendation. |
| Defaulter tracing | Follow-up, reminder, or return-to-care recommendation. |

If a narrower validated L1 recommendation cannot be found, keep `KEN-CC-L1-aa03884194` only if the rule truly depends on the overall screen-triage-treat approach, and mark the item as `needs_clinical_review`.

---

## DAK element-specific instructions

## 01_health_interventions

### Purpose

Represent health interventions and map them to validated L1 recommendations, workflows, decision logic, schedules, and indicators.

### Cleanup tasks

1. Replace invalid or legacy L1 links with clinician-validated L1 IDs.
2. Move original L1 IDs that are not clinician-validated into `legacy_l1_recommendation_ids`.
3. Convert semicolon-separated IDs to JSON arrays.
4. Classify each intervention by CDS relevance:

```json
"cds_relevance": "direct | indirect | programme_only"
```

5. Keep broad programme interventions as `programme_only`.
6. Use direct CDS relevance only for interventions that can drive a CDS card or rule.

### Suggested CDS-relevant interventions

| Intervention type | CDS relevance |
|---|---|
| HPV result management | Direct |
| VIA result management | Direct |
| Cytology result management | Direct |
| Suspected cancer referral | Direct |
| Post-treatment follow-up | Direct |
| Screening programme overview | Programme only |
| Resource availability guidance | Indirect |

---

## 02_personas

### Purpose

Define actors and personas involved in the DAK.

### Cleanup tasks

1. Ensure persona IDs follow a consistent pattern such as `CC.PER.001`.
2. Ensure scenario references use actual persona IDs, not descriptive labels such as `persona_woman_primary_hpv`.
3. Add actor or CDS-user classifications where needed:

```json
"cds_user_type": "clinician | client | program_manager | lab_user | referral_provider"
```

4. Identify whether each persona triggers, consumes, or only monitors CDS output.

### CDS role guidance

| Persona | CDS role |
|---|---|
| Nurse/Midwife | Primary CDS user |
| Clinical/Medical Officer | CDS user and validator |
| Laboratory Staff | Result producer |
| Referral Clinician | Referral receiver |
| Client | Subject of care, not direct CDS user unless client-facing app is planned |
| Community Health Promoter | Navigator/follow-up actor |
| County Coordinator | Reporting/dashboard user, not CDS Hooks user |

---

## 03_user_scenarios

### Purpose

Represent user stories, clinical journeys, and testable CDS scenarios.

### Cleanup tasks

1. Replace invalid persona references with valid `CC.PER.*` IDs.
2. Ensure each scenario links to a valid workflow, decision table, data element set, and validated L1 recommendation where appropriate.
3. Split very broad scenarios into smaller CDS-testable scenarios if necessary.
4. Add CDS test metadata:

```json
{
  "cds_hook_candidate": true,
  "cds_test_case_candidate": true,
  "clinical_review_status": "validated"
}
```

### Suggested scenario categories

| Scenario | Link to |
|---|---|
| Routine screening | Age/method selection decision table |
| HPV positive | HPV result and triage decision table |
| VIA positive | VIA result and ablation eligibility rules |
| Cytology abnormal | Cytology result and HPV triage rules |
| Suspected cancer | Urgent referral rule |
| Post-treatment follow-up | 12-month follow-up schedule and follow-up result rule |
| Missed appointment | Defaulter tracing or overdue follow-up rule |

---

## 04_workflows

### Purpose

Represent business processes and workflow steps.

### Cleanup tasks

1. Standardize workflow and step IDs.
2. Fix invalid transition references.
3. Keep workflows as process steps rather than full decision logic.
4. Link workflow steps to decision tables instead of embedding all branching text in the workflow step.
5. Replace L1 links with clinician-validated IDs.
6. Add CDS relevance fields where appropriate.

### Preferred workflow step structure

```json
{
  "step_id": "CC.WF.04.STEP.003",
  "actor_id": "CC.ACTOR.003",
  "activity": "Review HPV test result",
  "input_data_element_ids": ["CC.D.HPV.DE.001"],
  "output_data_element_ids": ["CC.D.HPV.DE.002"],
  "linked_decision_table_ids": ["CC.DT.03"],
  "linked_l1_recommendation_ids": ["KEN-CC-L1-validated"],
  "cds_relevant": true,
  "clinical_review_status": "validated"
}
```

Branching such as “if HPV positive and colposcopy unavailable, perform VIA triage” belongs in decision support, not in the workflow step itself.

---

## 05_core_data_dictionary

### Purpose

Define the atomic data elements and value sets required for workflows, CDS rules, schedules, indicators, and reporting.

This is the most important artifact for CDS Hooks readiness.

### Cleanup tasks

1. Populate missing data elements if the dictionary is empty or incomplete.
2. Replace incorrectly used L1 recommendation IDs with proper data element IDs.
3. Deduplicate synonyms and repeated clinical concepts.
4. Add coded value sets for decision-triggering variables.
5. Add flags for CDS and reporting use:

```json
{
  "required_for_cds": true,
  "required_for_reporting": true
}
```

### Minimum required CDS data elements

| Domain | Data elements |
|---|---|
| Demographics | Unique client ID, date of birth, age, sex/gender |
| Eligibility | HIV status, pregnancy status, previous screening, previous treatment |
| Screening method | HPV availability, VIA availability, cytology availability, selected screening method |
| HPV | HPV test performed, HPV result, HR-HPV positive/negative, result date |
| VIA | VIA performed, VIA result, VIA adequacy |
| Cytology | Cytology performed, cytology result, ASCUS status, >ASCUS status |
| Colposcopy | Colposcopy availability, colposcopy performed, colposcopy result |
| Biopsy/histology | Biopsy performed, histology result, CIN grade |
| Treatment eligibility | Ablation eligibility, lesion visibility, lesion size/extent, suspicion of cancer |
| Treatment | Treatment modality, ablation, cryotherapy, thermal ablation, LEEP, cone biopsy, treatment date |
| Referral | Referral required, referral reason, destination, urgency |
| Follow-up | Next screening due date, post-treatment follow-up due date, follow-up test result |
| Defaulter tracing | Appointment missed, reminder sent, return status |

### Example coded value set

```json
{
  "data_element_id": "CC.E.VIA.DE.001",
  "name": "VIA result",
  "data_type": "coded",
  "value_set": [
    "negative",
    "positive",
    "suspicious_for_cancer",
    "inadequate_or_uninterpretable"
  ],
  "required_for_cds": true,
  "required_for_reporting": true
}
```

Avoid using free-text-only values for CDS triggers.

---

## 06_decision_support_scheduling

### Purpose

Contain the main CDS Hooks-ready decision and scheduling logic.

Decision support and scheduling may remain in the same DAK element if that is how the WHO-style package is structured, but they must be separated into distinct internal sections.

### Cleanup tasks

1. Separate decision support rules from scheduling rules.
2. Convert decision rules into atomic, executable rules.
3. Retire flowchart fragments from CDS execution if they duplicate consolidated rules.
4. Ensure every executable rule has a trigger, input data elements, conditions, action, validated L1 link, and CDS Hook metadata.
5. Ensure every scheduling rule contains time logic only.
6. Fix the post-treatment positive follow-up inconsistency: positive follow-up should trigger the guideline-supported re-treatment/evaluation pathway, not just repeat testing unless the validated guideline specifically says so.
7. Replace over-broad L1 links with specific validated L1 links where possible.

### Decision rule structure

```json
{
  "rule_id": "CC.DT.03.R.001",
  "decision_table_id": "CC.DT.03",
  "rule_name": "HPV negative result",
  "trigger": "HPV screening result available",
  "conditions": [
    {
      "data_element_id": "CC.D.HPV.DE.002",
      "operator": "=",
      "value": "negative"
    }
  ],
  "actions": [
    {
      "action_type": "schedule_follow_up",
      "description": "Schedule routine rescreening according to validated guideline interval."
    }
  ],
  "linked_l1_recommendation_ids": ["KEN-CC-L1-validated"],
  "cds_hooks": {
    "candidate_hook": "patient-view",
    "card_indicator": "info",
    "card_summary": "HPV negative: schedule routine rescreening",
    "source_label": "Kenya Cervical Cancer Guidelines"
  },
  "cds_executable": true,
  "clinical_review_status": "validated"
}
```

### Scheduling rule structure

```json
{
  "schedule_id": "CC.S.05",
  "schedule_name": "Post-treatment follow-up",
  "trigger_event": "Treatment completed",
  "time_offset": {
    "value": 12,
    "unit": "months"
  },
  "due_event": "Post-treatment follow-up test",
  "linked_decision_table_ids": ["CC.DT.10"],
  "linked_l1_recommendation_ids": ["KEN-CC-L1-validated"],
  "cds_executable": true,
  "clinical_review_status": "validated"
}
```

### CDS Hooks mapping guidance

| Clinical logic | Candidate CDS Hook | Card indicator |
|---|---|---|
| Screening due | `patient-view` | `info` |
| Screening method selection | `patient-view` | `info` |
| HPV positive | `patient-view` | `warning` |
| VIA suspicious for cancer | `patient-view` | `critical` |
| Cytology >ASCUS | `patient-view` | `warning` |
| Treatment eligibility | `patient-view` or `order-sign` | `warning` |
| Referral required | `encounter-discharge` | `critical` |
| Follow-up overdue | `patient-view` or appointment workflow | `warning` |

---

## 07_indicators

### Purpose

Support monitoring, reporting, quality improvement, and KHIS/DHIS2 aggregation.

Indicators should not be treated as direct CDS execution rules.

### Cleanup tasks

1. Map numerator and denominator definitions to core data dictionary IDs.
2. Keep indicator L1 links at the programme or reporting level unless a direct clinical recommendation is clearly relevant.
3. Add reporting flags:

```json
{
  "reporting_only": true,
  "cds_executable": false
}
```

4. Make numerator and denominator logic computable with coded data elements and time periods.

### Required indicator fields

Where possible, include:

```json
{
  "linked_data_element_ids": [],
  "linked_l1_recommendation_ids": [],
  "reporting_only": true,
  "cds_executable": false,
  "clinical_review_status": "validated"
}
```

---

## 08_requirements

### Purpose

Define functional and non-functional system requirements and provide traceability to workflows, data elements, decision support, schedules, indicators, and validated L1 recommendations.

### Cleanup tasks

1. Replace invalid or legacy recommendation IDs with clinician-validated IDs.
2. Add traceability links to workflow steps, data elements, decision rules, schedules, and indicators.
3. Add testable acceptance criteria for CDS-related requirements.
4. Separate functional requirements from non-functional requirements if structurally possible.
5. Mark CDS-relevant requirements.

### Preferred functional requirement structure

```json
{
  "requirement_id": "CC.FXNREQ.006",
  "business_process_activity_id_and_description": "Support HPV-positive triage.",
  "acceptance_criteria": "When HPV result is positive, the system displays the next recommended triage or referral action based on colposcopy availability and VIA result.",
  "linked_workflow_step_ids": ["CC.WF.04.STEP.003"],
  "linked_decision_schedule_ids": ["CC.DT.03", "CC.DT.04"],
  "linked_data_element_ids": ["CC.D.HPV.DE.002", "CC.E.VIA.DE.001"],
  "linked_recommendation_ids": ["KEN-CC-L1-validated"],
  "cds_relevant": true,
  "clinical_review_status": "validated"
}
```

---

## Cross-artifact validation checks

Run these checks after editing.

### 1. L1 link validation

Every final `KEN-CC-L1-*` ID used in L2 must exist in `l1_recommendations_clinician_validated.xlsx`.

Output in `cross_artifact_validation_cleaned.json`:

```json
{
  "unique_l1_ids_used_in_l2": 0,
  "valid_l1_ids": 0,
  "invalid_l1_ids": 0,
  "invalid_l1_id_list": []
}
```

### 2. Internal ID validation

Every referenced ID should resolve to a defined ID.

| Referenced field | Must exist in |
|---|---|
| `persona_id` | `02_personas` |
| `actor_id` | `02_personas` or workflow actor registry |
| `scenario_id` | `03_user_scenarios` |
| `workflow_id` | `04_workflows` |
| `workflow_step_id` | `04_workflows` |
| `data_element_id` | `05_core_data_dictionary` |
| `decision_table_id` | `06_decision_support_scheduling` |
| `rule_id` | `06_decision_support_scheduling` |
| `schedule_id` | `06_decision_support_scheduling` |
| `indicator_id` | `07_indicators` |
| `requirement_id` | `08_requirements` |

### 3. CDS readiness validation

Every CDS-executable rule must have:

| Field | Required |
|---|---|
| Rule ID | Yes |
| Trigger | Yes |
| Input data elements | Yes |
| Conditions | Yes |
| Action | Yes |
| Validated L1 ID | Yes |
| CDS Hook candidate | Yes |
| Card summary | Yes |
| Clinical review status | Yes |
| Source/provenance | Yes |

Rules missing any required field should be marked:

```json
{
  "cds_executable": false,
  "requires_clinical_review": true
}
```

### 4. Flowchart fragment validation

Decision support rows that are flowchart fragments should not be used as standalone executable CDS rules unless transformed into complete rules.

Use:

```json
{
  "cds_executable": false,
  "clinical_review_status": "retired_from_cds",
  "retirement_reason": "Flowchart fragment superseded by consolidated decision rule."
}
```

---

## Editing sequence

Use this order to avoid breaking dependencies.

### Step 1: Unpack and inventory

1. Extract the DAK ZIP.
2. Remove temporary lock files.
3. Read all artifact JSON files.
4. Read all artifact XLSX files only as paired human-readable outputs.
5. Read `l1_recommendations_clinician_validated.xlsx` as canonical L1.
6. Read `l1_recommendations.xlsx` only for L1 comparison tracking.
7. Load the previous L2 audit workbook if present.

### Step 2: Build registries

Build registries for:

```text
validated_l1_ids
original_l1_ids
persona_ids
actor_ids
scenario_ids
workflow_ids
workflow_step_ids
data_element_ids
decision_table_ids
decision_rule_ids
schedule_ids
indicator_ids
requirement_ids
```

### Step 3: Build L1 comparison map

Compare original L1 and clinician-validated L1.

Create:

```text
l1_clinician_change_tracking.json
```

Use this only for provenance and improvement logs. Do not use unmatched original L1 items to justify final L2 linkage.

### Step 4: Normalize recommendation links

For every artifact:

1. Convert semicolon-separated recommendation IDs to arrays in JSON.
2. Validate all final recommendation IDs against clinician-validated L1.
3. Replace invalid or legacy links where a validated equivalent is clear.
4. Move original-only IDs to `legacy_l1_recommendation_ids`.
5. Mark unresolved items clearly.
6. Log every change.

### Step 5: Clean foundational artifacts

Clean in this order:

```text
02_personas
05_core_data_dictionary
04_workflows
06_decision_support_scheduling
03_user_scenarios
01_health_interventions
07_indicators
08_requirements
```

Rationale:

1. Personas and data elements are foundational.
2. Workflows depend on personas and data elements.
3. Decision support depends on workflows and data elements.
4. Scenarios test workflows and decisions.
5. Interventions summarize clinical actions.
6. Indicators and requirements should be reconciled after logic stabilizes.

### Step 6: Regenerate XLSX files from cleaned JSON

For each DAK element:

1. Preserve existing sheet names where possible.
2. Preserve column order where possible.
3. Add new cleanup columns at the end, such as:
   - `canonical_l1_recommendation_ids`
   - `legacy_l1_recommendation_ids`
   - `cds_executable`
   - `cds_hook_candidate`
   - `clinical_review_status`
   - `cleanup_notes`
4. Use readable spreadsheet formatting: frozen header row, wrapped text, adjusted column widths, and filters.
5. Do not overwrite `extraction_log.json` or `validation_report.json`.

### Step 7: Generate logs

For every DAK element, create:

```text
improvements_log.json
```

At root level, create:

```text
improvement_master_log.json
cross_artifact_validation_cleaned.json
l1_clinician_change_tracking.json
```

### Step 8: Rename artifact files

Rename every cleaned artifact pair:

```text
artifact.json -> 04_workflows_artifact.json
artifact.xlsx -> 04_workflows_artifact.xlsx
```

Use the correct folder number and element name.

### Step 9: Package outputs

Create:

```text
Kenya_Cervical_Cancer_Template_DAK_cleaned_CDS_ready.zip
Kenya_Cervical_Cancer_Template_DAK_cleanup_summary.xlsx
```

---

## Summary workbook requirements

Create a workbook called:

```text
Kenya_Cervical_Cancer_Template_DAK_cleanup_summary.xlsx
```

Suggested sheets:

| Sheet | Contents |
|---|---|
| `Summary` | Overall counts and readiness assessment. |
| `DAK_Element_Changes` | One row per DAK element with reviewed/updated/retired/unresolved counts. |
| `L1_Link_Validation` | All final L1 IDs used in L2 and whether they exist in clinician-validated L1. |
| `L1_Clinician_Changes` | Comparison of original L1 versus clinician-validated L1. |
| `Retired_From_CDS` | Flowchart fragments and redundant items excluded from CDS execution. |
| `Clinical_Review_Needed` | Items still requiring clinician review. |
| `CDS_Hooks_Candidates` | Candidate hooks, cards, triggers, and linked rules. |
| `Data_Element_Coverage` | CDS rules mapped to required data elements. |
| `Internal_ID_Validation` | Broken or unresolved internal references. |

---

## Definition of done

The task is complete only when all of these are true:

| Criterion | Expected result |
|---|---|
| DAK ZIP unpacked and cleaned | Yes |
| Original WHO-style folder structure preserved | Yes |
| All artifact JSON files renamed | Yes |
| All artifact XLSX files renamed | Yes |
| `extraction_log.json` retained in every DAK element | Yes |
| `validation_report.json` retained in every DAK element | Yes |
| `improvements_log.json` added to every DAK element | Yes |
| Clinician-validated L1 used as canonical source | Yes |
| Original L1 used only for change tracking | Yes |
| `l1_clinician_change_tracking.json` created | Yes |
| Invalid L1 links corrected or flagged | Yes |
| Scenario-persona links valid | Yes |
| Workflow transitions valid or flagged | Yes |
| Core data elements available for CDS rules | Yes |
| Decision rules atomic and CDS-ready | Yes |
| Scheduling logic separated from decision logic | Yes |
| Flowchart fragments retired from CDS execution or transformed | Yes |
| CDS Hooks metadata added where appropriate | Yes |
| Cross-artifact validation file generated | Yes |
| Improvement master log generated | Yes |
| Cleanup summary workbook generated | Yes |
| Final cleaned CDS-ready ZIP produced | Yes |

---

## Command to execute the final edit step

Use this instruction in the next step:

```text
Proceed with the final edits. Use the uploaded Kenya Cervical Cancer Template DAK ZIP, the clinician-validated L1 recommendations as the canonical L1 source, the original L1 recommendations only to track clinician changes against LLM-extracted L1 recommendations, and the previous L2 audit findings as the cleanup guide. Clean each DAK element separately, preserve the WHO SMART Guidelines DAK structure, retain every extraction_log.json and validation_report.json, add improvements_log.json to each DAK element folder, rename each artifact JSON/XLSX pair using the folder number and DAK element name, generate l1_clinician_change_tracking.json, cross_artifact_validation_cleaned.json, and improvement_master_log.json, then return a cleaned CDS-ready ZIP plus a summary workbook of changes.
```
