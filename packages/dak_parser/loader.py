"""
DAK parser / loader.

Loads the eight Kenya Cervical Cancer Template DAK artifacts from a directory and
exposes them as normalized Python structures. This is Phase 1 of the build sequence
(DAK ingestion) and the single source every downstream package reads from.

The loader is deliberately tolerant: the DAK ships with known data-quality issues
(e.g. the string "null" in schedule actor fields, 0-step workflows, mixed-case hit
policies). We surface those as `warnings` rather than crashing, so ingestion is
re-runnable across L2 -> L2.1 revisions.

Usage:
    dak = DAK.load("/path/to/Kenya Cervical Cancer Template DAK")
    dak.elements            # 287 data-dictionary elements (flattened, with module)
    dak.decision_tables     # {decision_id: CompiledTableSource}
    dak.schedules           # {schedule_id: [items]}
    dak.indicators          # 22 indicators
    dak.l1_recommendations  # 54 L1 recs (dual IDs)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

L1_ID_RE = re.compile(r"KEN-CC-[A-Za-z0-9]+-[0-9a-f]+")


def _read_json(p: Path) -> dict:
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _artifact_path(root: Path, folder: str) -> Path:
    """Support both the legacy layout (`<folder>/artifact.json`) and the cleaned
    CDS-ready layout (`<folder>/<folder>_artifact.json`)."""
    fp = root / folder
    legacy = fp / "artifact.json"
    if legacy.exists():
        return legacy
    renamed = sorted(fp.glob("*_artifact.json"))
    if renamed:
        return renamed[0]
    raise FileNotFoundError(f"No artifact JSON found in {fp}")


def _resolve_dak_root(path: str | Path) -> Path:
    """Accept either the DAK root itself, or a parent folder that contains it
    (e.g. the '..._cleaned' wrapper the cleaned ZIP extracts into)."""
    p = Path(path)
    if (p / "05_core_data_dictionary").exists():
        return p
    for x in sorted(p.iterdir()) if p.is_dir() else []:
        if x.is_dir() and (x / "05_core_data_dictionary").exists():
            return x
    raise FileNotFoundError(f"Could not find DAK root under {p}")


def _sheets(artifact: dict) -> dict:
    return artifact.get("sheets", {})


@dataclass
class DAK:
    root: Path
    artifacts: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    improvements: dict[str, dict] = field(default_factory=dict)   # cleaned-DAK logs

    # ---- normalized views -------------------------------------------------
    elements: list[dict] = field(default_factory=list)               # data dictionary
    element_by_id: dict[str, dict] = field(default_factory=dict)
    decision_table_register: list[dict] = field(default_factory=list)
    decision_tables: dict[str, list[dict]] = field(default_factory=dict)  # id -> rule rows
    schedule_register: list[dict] = field(default_factory=list)
    schedules: dict[str, list[dict]] = field(default_factory=dict)
    indicators: list[dict] = field(default_factory=list)
    l1_recommendations: list[dict] = field(default_factory=list)
    interventions: list[dict] = field(default_factory=list)
    requirements: dict[str, list[dict]] = field(default_factory=dict)
    workflows: dict[str, Any] = field(default_factory=dict)
    personas: dict[str, Any] = field(default_factory=dict)

    # ---- loading ----------------------------------------------------------
    @classmethod
    def load(cls, root: str | Path) -> "DAK":
        root = _resolve_dak_root(root)
        if not _artifact_path(root, "05_core_data_dictionary").exists():
            raise FileNotFoundError(
                f"Not a DAK directory (missing core data dictionary artifact): {root}"
            )
        dak = cls(root=root)
        dak._load_all()
        return dak

    def _load_all(self) -> None:
        def art(name: str) -> dict:
            a = _read_json(_artifact_path(self.root, name))
            self.artifacts[name] = a
            # capture the cleaned-DAK improvements log if present
            for candidate in (self.root / name / "improvements_log.json",):
                if candidate.exists():
                    try:
                        self.improvements[name] = _read_json(candidate)
                    except Exception:
                        pass
            return a

        # 01 health interventions / L1 recommendations
        hi = _sheets(art("01_health_interventions"))
        self.l1_recommendations = hi.get("l1_recommendations", [])
        self.interventions = hi.get("health_interventions", [])

        # 02 personas
        self.personas = _sheets(art("02_personas"))

        # 04 workflows
        self.workflows = _sheets(art("04_workflows"))
        wf_steps = self.workflows.get("workflow_steps", {})
        if isinstance(wf_steps, dict) and wf_steps.get("CC.A Registration", None) == []:
            self.warnings.append("workflow 'CC.A Registration' has 0 steps (must be authored)")

        # 05 core data dictionary -> flatten module groups
        dd = _sheets(art("05_core_data_dictionary"))
        modules = dd.get("modules", {})
        for module_name, rows in modules.items():
            for r in rows:
                r = dict(r)
                r["_module"] = module_name
                deid = r.get("data_element_id")
                self.elements.append(r)
                if deid:
                    # last-wins on dup ids; DAK has some child-row dup warnings
                    self.element_by_id[deid] = r

        # 06 decision support & scheduling
        ds = _sheets(art("06_decision_support_scheduling"))
        self.decision_table_register = ds.get("decision_table_register", [])
        self.decision_tables = ds.get("decision_tables", {})
        self.schedule_register = ds.get("schedule_register", [])
        self.schedules = ds.get("schedules", {})
        self._coerce_null_strings()

        # 07 indicators
        ind = _sheets(art("07_indicators"))
        self.indicators = ind.get("indicators", [])
        self.indicator_de_map = ind.get("indicator_data_element_mappings", [])

        # 08 requirements
        rq = _sheets(art("08_requirements"))
        self.requirements = {
            "functional": rq.get("functional_requirements", []),
            "nonfunctional": rq.get("nonfunctional_requirements", []),
            "traceability": rq.get("requirement_traceability", []),
        }

    def _coerce_null_strings(self) -> None:
        """Several schedule rows store the literal string 'null'. Coerce to None
        and record a data-quality warning (per v2 build-instructions §5.4)."""
        fixed = 0
        for sid, items in self.schedules.items():
            for it in items:
                for k in ("responsible_actor", "escalation_missed_service_action"):
                    if it.get(k) == "null":
                        it[k] = None
                        it["_needs_clinical_review"] = True
                        fixed += 1
        if fixed:
            self.warnings.append(
                f"coerced {fixed} literal 'null' strings in schedule actor/escalation fields"
            )

    # ---- helpers used by binding + engine ---------------------------------
    def rule_input_concepts(self) -> set[str]:
        """All distinct L1 concept ids used as decision-table rule INPUTS."""
        out: set[str] = set()
        for rows in self.decision_tables.values():
            for r in rows:
                for i in ("input_1", "input_2", "input_3", "input_4"):
                    inp = r.get(i)
                    if isinstance(inp, dict) and inp.get("data_element_id"):
                        out.add(inp["data_element_id"])
        return out

    def element_l1_crosswalk(self) -> dict[str, set[str]]:
        """L2 element id -> set of L1 concept ids parsed from source_recommendation_id.
        Cleaned DAK stores this as a list; legacy stored a delimited string."""
        cw: dict[str, set[str]] = {}
        for e in self.elements:
            deid = e.get("data_element_id")
            src = e.get("source_recommendation_id") or ""
            if isinstance(src, list):
                found = [x for item in src for x in L1_ID_RE.findall(str(item))]
            else:
                found = L1_ID_RE.findall(str(src))
            cw.setdefault(deid, set()).update(found)
        return cw

    def summary(self) -> dict:
        return {
            "elements": len(self.elements),
            "elements_with_fhir": sum(1 for e in self.elements if e.get("fhir_resource")),
            "elements_with_value_set": sum(1 for e in self.elements if e.get("input_options")),
            "decision_tables": len(self.decision_tables),
            "rules": sum(len(v) for v in self.decision_tables.values()),
            "schedules": len(self.schedules),
            "schedule_items": sum(len(v) for v in self.schedules.values()),
            "indicators": len(self.indicators),
            "l1_recommendations": len(self.l1_recommendations),
            "interventions": len(self.interventions),
            "warnings": self.warnings,
        }
