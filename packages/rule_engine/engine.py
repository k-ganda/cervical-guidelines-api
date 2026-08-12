"""
The rule engine: the clinical authority.

Evaluates a compiled DAK decision table against patient facts and returns a CDSResult.
Facts are supplied in L2 element space (that is what forms write); the engine resolves
each rule's L1 input concept to its bound L2 element via the concept-binding report,
then normalizes both the stored value and the rule value before comparison.

Guarantees (v2 build instructions §5.3, rules 1-12):
  * Missing required fact         -> insufficient_data (never guess)
  * Unbound rule-input concept    -> binding_unresolved_needs_review (never guess)
  * UNIQUE policy, >1 match        -> conflict_detected_needs_clinical_review
  * Respects FIRST vs UNIQUE hit policy
  * Every result carries rule id, source, provenance, review status, explanation
  * ML/LLM never enter here; this is deterministic
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from packages.rule_engine.compiler import CompiledRule, CompiledTable
from packages.rule_engine.cds_output import (
    CDSResult, FactUsed, SOURCE_DOC,
    OK, INSUFFICIENT_DATA, BINDING_UNRESOLVED, CONFLICT, NO_MATCH,
    SANDBOX_WITHHELD, BLOCKED, RULE_NONCOMPUTABLE, RULE_DISABLED,
)
from packages.binding.seeder import BindingReport
from packages.binding.normalize import Normalizer


@dataclass
class PatientFacts:
    """Facts keyed by L2 element id (what forms produce), plus metadata."""
    values: dict[str, object]          # l2_element_id -> raw value
    patient_id: str = ""
    encounter_id: str = ""

    def get_l2(self, l2_id: str | None):
        if l2_id is None:
            return None
        return self.values.get(l2_id)


_URGENT_KEYWORDS = ("refer", "urgent", "immediate")
_CRITICAL_KEYWORDS = ("suspected cancer", "suspicious for cancer", "cancer")


def _numeric(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clean_ids(ids) -> list[str]:
    """Drop things a clinician can't act on from a 'missing' list: value-option
    sub-elements (…OPT.NNN) and still-unbound guideline concepts (KEN-CC-L1-*)."""
    out = []
    for x in ids:
        if ".OPT." in x or x.startswith("KEN-CC-L1-"):
            continue
        if x not in out:
            out.append(x)
    return out


class RuleEngine:
    def __init__(self, bindings: BindingReport, normalizer: Normalizer,
                 mode: str = "sandbox", rule_configs: dict | None = None):
        self.bind = bindings.index()            # l1_concept_id -> ConceptBinding
        self.norm = normalizer
        self.mode = mode                        # 'sandbox' (pilot) | 'production'
        self.rule_configs = rule_configs or {}  # rule_id -> cds_rule_configs overlay

    # ---- condition evaluation --------------------------------------------
    def _eval_condition(self, cond, facts: PatientFacts):
        """Return (matched: bool|None, fact_used|None, problem|None).
        matched=None means undecidable (missing fact / unbound concept)."""
        binding = self.bind.get(cond.l1_concept_id)
        if binding is None or binding.binding_status.startswith("orphan"):
            return None, None, ("unbound", cond.l1_concept_id)
        # governed "no field / not mapped locally" outcomes -> non-computable, not a nag
        if binding.binding_status in ("not_captured", "intentionally_not_mapped",
                                      "retired_from_local_workflow"):
            return None, None, ("noncomputable", cond.l1_concept_id)
        if binding.primary_l2_element_id is None:
            return None, None, ("unbound", cond.l1_concept_id)  # ambiguous, not yet resolved

        l2_id = binding.primary_l2_element_id
        raw = facts.get_l2(l2_id)
        if raw is None:
            return None, None, ("missing", cond.l1_concept_id)

        fu = FactUsed(
            l1_concept_id=cond.l1_concept_id, l2_element_id=l2_id,
            raw_value=raw, normalized_code=self.norm.normalize(raw, l2_id),
        )

        op = cond.operator
        if op in ("=", "!="):
            match = self.norm.values_match(raw, cond.value, l2_id)
            match = match if op == "=" else (not match)
        else:  # numeric inequalities
            lhs, rhs = _numeric(raw), _numeric(cond.value)
            if lhs is None or rhs is None:
                return None, fu, ("non_numeric", cond.l1_concept_id)
            match = {">": lhs > rhs, ">=": lhs >= rhs,
                     "<": lhs < rhs, "<=": lhs <= rhs}[op]
        return bool(match), fu, None

    def _eval_rule(self, rule: CompiledRule, facts: PatientFacts):
        """AND across conditions. Returns (status, facts_used, problems).
        status in {'match','no_match','undecidable','default'}.
        'no_match' = a condition is definitively false (rule eliminated);
        'undecidable' = no false condition, only missing/unbound inputs remain."""
        if rule.is_default:
            return "default", [], []
        used, problems = [], []
        has_false = False
        for c in rule.conditions:
            matched, fu, problem = self._eval_condition(c, facts)
            if fu:
                used.append(fu)
            if problem:
                problems.append(problem)
            elif matched is False:
                has_false = True
        if has_false:
            return "no_match", used, problems        # eliminated (a condition is false)
        if problems:
            return "undecidable", used, problems      # only missing/unbound remain
        return "match", used, problems

    # ---- public ----------------------------------------------------------
    def evaluate(self, table: CompiledTable, facts: PatientFacts) -> CDSResult:
        audit_id = str(uuid.uuid4())
        base = dict(
            patient_id=facts.patient_id, encounter_id=facts.encounter_id,
            decision_table_id=table.decision_id, hit_policy=table.hit_policy,
            source_document=SOURCE_DOC, audit_log_id=audit_id,
            clinical_review_status=table.clinical_review_status,
            technical_review_status=table.technical_review_status,
            provenance=table.provenance,
        )

        matches: list[tuple[CompiledRule, list[FactUsed]]] = []
        default_rule: CompiledRule | None = None
        unbound: set[str] = set()
        missing: set[str] = set()
        noncomputable: set[str] = set()
        all_used: list[FactUsed] = []
        # per-rule progress, to scope the "what to capture next" hint to the rule
        # that is closest to firing rather than the union across the whole table
        rule_progress: list[tuple[int, list[str]]] = []   # (satisfied_count, capturable_missing)

        for rule in table.rules:
            # disabled rules are truly non-executable: they must not match, produce a
            # card, create an alert, or drive side effects (audit §2.2)
            cfg = self._rule_config(rule.rule_id)
            if cfg and cfg.get("enabled") is False:
                continue
            status, used, problems = self._eval_rule(rule, facts)
            all_used.extend(used)
            r_missing = []
            for p in problems:
                if p[0] == "unbound":
                    unbound.add(p[1])
                elif p[0] == "noncomputable":
                    noncomputable.add(p[1])
                elif p[0] in ("missing", "non_numeric"):
                    missing.add(p[1])
                    r_missing.append(p[1])
            if status == "default":
                default_rule = default_rule or rule
            elif status == "match":
                matches.append((rule, used))
            elif status == "undecidable" and not rule.is_default:
                satisfied = len(used)
                if satisfied and _clean_ids(r_missing):
                    rule_progress.append((satisfied, _clean_ids(r_missing)))
            if table.hit_policy == "FIRST" and matches:
                break

        missing_clean = _clean_ids(missing)
        # closest rule = most inputs already satisfied, fewest still needed
        next_step: list[str] = []
        if rule_progress:
            rule_progress.sort(key=lambda x: (-x[0], len(x[1])))
            next_step = rule_progress[0][1]

        # 1) a fully-matching rule fires (highest priority)
        if matches:
            if table.hit_policy == "UNIQUE" and len(matches) > 1:
                return CDSResult(**base, recommendation_type=CONFLICT,
                                 explanation_for_clinician=(
                                     f"{len(matches)} rules matched under UNIQUE hit policy: "
                                     + ", ".join(r.rule_id for r, _ in matches)),
                                 input_facts_used=all_used)
            rule, used = matches[0]
            return self._result_from_rule(base, rule, used)

        # 2) a rule is one capturable (already-bound) fact away from firing ->
        #    ask for that specific data rather than raising the binding gate
        if rule_progress:
            return CDSResult(**base, recommendation_type=INSUFFICIENT_DATA,
                             missing_required_facts=sorted(missing_clean),
                             missing_for_next_step=sorted(next_step),
                             unbound_concepts=sorted(unbound),
                             explanation_for_clinician="Insufficient data for this decision.",
                             input_facts_used=all_used)

        # 3) hard stop: the decision is blocked by an unbound input concept
        if unbound:
            return CDSResult(**base, recommendation_type=BINDING_UNRESOLVED,
                             unbound_concepts=sorted(unbound),
                             explanation_for_clinician=(
                                 f"{len(unbound)} guideline concept(s) on this pathway are not yet "
                                 "bound to a captured field. Resolve them under Binding review / "
                                 "DAK governance before this decision can run."),
                             input_facts_used=all_used)

        # 3b) a required concept is governed as not-captured / not-mapped locally ->
        #     the rule is non-computable here; do NOT keep nagging as "unresolved"
        if noncomputable:
            return CDSResult(**base, recommendation_type=RULE_NONCOMPUTABLE,
                             unbound_concepts=sorted(noncomputable),
                             explanation_for_clinician=(
                                 "This decision cannot be computed in the local workflow because a "
                                 "required guideline concept is marked not-captured / not-mapped. "
                                 "It is intentionally withheld (see Binding review)."),
                             input_facts_used=all_used)

        # 4) bound-but-missing facts, no single rule close -> insufficient data (union)
        if missing_clean:
            return CDSResult(**base, recommendation_type=INSUFFICIENT_DATA,
                             missing_required_facts=sorted(missing_clean),
                             missing_for_next_step=sorted(missing_clean)[:3],
                             unbound_concepts=sorted(unbound),
                             explanation_for_clinician="Insufficient data for this decision.",
                             input_facts_used=all_used)

        # 5) default / otherwise row — fires clinically ONLY if explicitly marked a
        #    safe fallback; otherwise empty/partial facts must NOT yield a clinical rec
        if default_rule is not None:
            if getattr(default_rule, "safe_fallback", False):
                res = self._result_from_rule(base, default_rule, all_used)
                res.explanation_for_clinician = ("[safe fallback row] "
                                                 + res.explanation_for_clinician)
                return res
            return CDSResult(**base, recommendation_type=INSUFFICIENT_DATA,
                             missing_for_next_step=[],
                             explanation_for_clinician=(
                                 "No patient-specific rule matched. The only remaining row "
                                 "has no conditions and is not marked a safe fallback, so no "
                                 "clinical recommendation is issued (verify in clinical review)."),
                             input_facts_used=all_used)

        # 5) nothing matched
        return CDSResult(**base, recommendation_type=NO_MATCH,
                         explanation_for_clinician="No rule matched the supplied facts.",
                         input_facts_used=all_used)

    def _execution_status(self, rule: CompiledRule) -> str:
        """Safety-by-design: the cleaned DAK's review status + executability decide
        whether a rule may drive care.
          blocked   -> DAK marks it non-executable; never present as actionable
          validated -> clinician-validated + executable; may fire in production
          sandbox   -> everything else (needs clinical review); pilot only"""
        if not rule.cds_executable:
            return "blocked"
        if str(rule.clinical_review_status).lower() == "validated":
            return "validated"
        return "sandbox"

    def _card_indicator(self, rule: CompiledRule):
        """Prefer the DAK's precomputed card indicator/summary (cleaned DAK); fall
        back to keyword derivation on the legacy DAK."""
        hook = rule.cds_hooks or {}
        ind = (hook.get("card_indicator") or "").strip().lower()
        summary = hook.get("card_summary")
        if ind in ("info", "warning", "critical"):
            return ind, summary
        text = f"{rule.output} {rule.action} {rule.alert_text or ''}".lower()
        if (rule.alert_text and any(k in rule.alert_text.lower() for k in _CRITICAL_KEYWORDS)) \
                or any(k in text for k in _CRITICAL_KEYWORDS):
            return "critical", summary
        if any(k in text for k in _URGENT_KEYWORDS):
            return "warning", summary
        return "info", summary

    def _result_from_rule(self, base: dict, rule: CompiledRule, used: list[FactUsed]) -> CDSResult:
        base = {k: v for k, v in base.items()
                if k not in ("clinical_review_status", "technical_review_status", "provenance")}
        indicator, dak_summary = self._card_indicator(rule)
        urgency = {"critical": "critical", "warning": "urgent", "info": "routine"}[indicator]
        exec_status = self._execution_status(rule)

        common = dict(
            rule_id=rule.rule_id,
            rule_version=(rule.provenance or {}).get("printed_page", ""),
            recommendation=dak_summary or rule.output,
            action=rule.action or rule.output,
            output_type=rule.output_type,
            urgency=urgency, card_indicator=indicator, alert_text=rule.alert_text,
            explanation_for_clinician=rule.guidance or rule.output,
            input_facts_used=used,
            clinical_review_status=rule.clinical_review_status,
            technical_review_status=rule.technical_review_status,
            execution_status=exec_status,
            linked_l1_recommendation_ids=rule.linked_l1_recommendation_ids,
            unresolved_l1_references=rule.unresolved_l1_references,
            provenance=rule.provenance or base.get("provenance", {}),
        )

        # blocked: DAK says not executable -> never actionable, in any mode
        if exec_status == "blocked":
            common.update(recommendation_type=BLOCKED, urgency="routine",
                          explanation_for_clinician=(
                              "This rule is marked non-executable in the DAK and is withheld "
                              "pending clinical review. " + (rule.guidance or "")))
            return CDSResult(**base, **common)

        # sandbox rule in production mode -> withhold the recommendation
        if exec_status == "sandbox" and self.mode == "production":
            common.update(recommendation_type=SANDBOX_WITHHELD,
                          explanation_for_clinician=(
                              "This rule has not completed clinical review and is withheld in "
                              "production mode. It is available in sandbox for testing."))
            return CDSResult(**base, **common)

        common.update(recommendation_type=OK)
        res = CDSResult(**base, **common)
        self._decorate(res, rule)
        return res

    def _decorate(self, res: CDSResult, rule) -> None:
        """Attach the push-CDS/alert layer fields derived from the rule + DAK."""
        from packages.rule_engine.severity import classify, snooze_options_for
        res.action_code = getattr(rule, "action_code", "no_action_required")
        sev, blocking, scope = classify(res, config=self._rule_config(rule.rule_id))
        res.severity_class, res.blocking, res.block_scope = sev, blocking, scope
        res.snooze_options = snooze_options_for(sev)
        res.field_targets = [c.l1_concept_id for c in rule.conditions]
        page = (rule.provenance or {}).get("printed_page")
        if page:
            res.guideline_page_refs = [page]
        res.alert_fingerprint = self._fingerprint(res)

    def _rule_config(self, rule_id: str) -> dict | None:
        return (self.rule_configs or {}).get(rule_id)

    @staticmethod
    def _fingerprint(res: CDSResult) -> str:
        import hashlib
        facts = "|".join(sorted(f"{f.l2_element_id}={f.normalized_code}"
                                for f in res.input_facts_used))
        raw = f"{res.patient_id}|{res.encounter_id}|{res.rule_id}|{facts}|{res.severity_class}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]
