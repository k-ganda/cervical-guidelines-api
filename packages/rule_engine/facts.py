"""
FactContextBuilder (plan §5.3).

Merges the facts a CDS evaluation should see, so the system stops re-asking for
things it already knows (age, HIV status, pregnancy status, prior results). This is
the direct fix for the "insufficient data / re-enter age" problem: a registered
client's demographics are injected as facts against every matching DAK element, so
demographic inputs no longer show up as "missing".

Priority (highest wins):
    pending form value > latest episode observation > patient demographics(derived/profile)

Safety rule: a value that comes from the patient profile / derived / a prior episode
is `confirmed_current=False`. For RED rules a caller must treat an unconfirmed value
as missing until confirmed in-encounter (enforced by the severity/completeness layer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# demographic -> how to detect the matching L2 elements by label
_DEMOGRAPHIC_LABEL_MATCH = {
    "age": lambda lbl: lbl.strip() == "age" or lbl.startswith("age ") or "client age" in lbl or "woman's age" in lbl,
    "hiv_status": lambda lbl: "hiv" in lbl and "status" in lbl,
    "pregnancy_status": lambda lbl: "pregnan" in lbl and "status" in lbl or lbl.strip() in ("pregnancy status", "pregnancy"),
}


@dataclass
class MergedFacts:
    values: dict                              # l2_element_id -> raw value (what the engine reads)
    sources: dict = field(default_factory=dict)   # l2_element_id -> 'pending'|'observation'|'profile'|'derived'
    confirmed_current: dict = field(default_factory=dict)  # l2_element_id -> bool

    def as_patient_facts(self, patient_id="", encounter_id=""):
        from packages.rule_engine.engine import PatientFacts
        return PatientFacts(values=dict(self.values), patient_id=patient_id, encounter_id=encounter_id)


class FactContextBuilder:
    def __init__(self, dak):
        self.dak = dak
        self._demographic_elements = self._index_demographic_elements()

    def _index_demographic_elements(self) -> dict[str, list[str]]:
        idx: dict[str, list[str]] = {k: [] for k in _DEMOGRAPHIC_LABEL_MATCH}
        for e in self.dak.elements:
            eid = e.get("data_element_id", "")
            if ".OPT." in eid:
                continue
            lbl = (e.get("data_element_label") or "").lower()
            for demo, match in _DEMOGRAPHIC_LABEL_MATCH.items():
                try:
                    if match(lbl):
                        idx[demo].append(eid)
                except Exception:
                    pass
        return idx

    @staticmethod
    def _age(patient) -> str | None:
        if getattr(patient, "age", None):
            return str(patient.age)
        bd = getattr(patient, "birth_date", None)
        if bd:
            try:
                y = date.fromisoformat(str(bd))
                today = date.today()
                return str(today.year - y.year - ((today.month, today.day) < (y.month, y.day)))
            except Exception:
                return None
        return None

    def build(self, patient, episode_observations: dict, pending_values: dict | None = None) -> MergedFacts:
        mf = MergedFacts(values={})

        # 3) patient demographics / derived (lowest priority) — injected into EVERY
        #    matching element so a rule finds it regardless of which element it uses
        demo_values = {
            "age": (self._age(patient), "derived" if not getattr(patient, "age", None) else "profile"),
            "hiv_status": (getattr(patient, "hiv_status", None), "profile"),
            "pregnancy_status": (getattr(patient, "pregnancy_status", None), "profile"),
        }
        for demo, (val, src) in demo_values.items():
            if not val:
                continue
            for eid in self._demographic_elements.get(demo, []):
                mf.values[eid] = val
                mf.sources[eid] = src
                # profile/derived demographics are not encounter-confirmed
                mf.confirmed_current[eid] = False

        # 2) episode observations
        for eid, val in (episode_observations or {}).items():
            mf.values[eid] = val
            mf.sources[eid] = "observation"
            mf.confirmed_current[eid] = True

        # 1) pending form values (highest priority)
        for eid, val in (pending_values or {}).items():
            if val in (None, ""):
                continue
            mf.values[eid] = val
            mf.sources[eid] = "pending"
            mf.confirmed_current[eid] = True

        return mf
