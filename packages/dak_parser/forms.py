"""
Form-schema generator: turns DAK data-dictionary elements into renderable form
schemas, grouped by module. The frontend renders these dynamically, so the registry
forms come straight from the DAK (single source) rather than being hand-coded — when
the L2.1 field validation changes an element, the form changes with it.

Option elements (ids ending in .OPT.NNN) are folded into their parent as choices,
so a select renders instead of a separate field per option.
"""
from __future__ import annotations

import re

_OPT_RE = re.compile(r"\.OPT\.\d+$")

# The 14 capture modules in dictionary order (letters are the dictionary's, which
# are canonical per the v2 build instructions).
MODULE_ORDER = [
    "CC.A Registration", "CC.B Eligibility history", "CC.C Symptoms examination",
    "CC.D HPV testing", "CC.E VIA", "CC.F Cytology", "CC.G Colposcopy biopsy",
    "CC.H Histopathology", "CC.I Treatment eligibility", "CC.J Precancer treatment",
    "CC.K Referral navigation", "CC.L Follow-up surveillance", "CC.M Record closure",
    "CC.Configuration",
]

_TYPE_MAP = {
    "date": "date", "datetime": "datetime-local", "boolean": "boolean",
    "integer": "number", "decimal": "number", "number": "number",
    "coded": "select", "codeableconcept": "select", "text": "text", "string": "text",
}


def _field_type(el: dict) -> str:
    dt = (el.get("data_type") or "").strip().lower()
    if el.get("input_options"):
        return "select"
    return _TYPE_MAP.get(dt, "text")


def _options(el: dict, children: list[dict]) -> list[dict]:
    opts = []
    # child OPT elements first (they carry human labels)
    for c in children:
        opts.append({"value": c.get("data_element_label") or c["data_element_id"],
                     "code": c["data_element_id"]})
    if opts:
        return opts
    # else parse input_options
    io = el.get("input_options")
    if isinstance(io, list):
        for o in io:
            if isinstance(o, dict):
                opts.append({"value": o.get("option_label") or o.get("option_id"),
                             "code": o.get("option_id")})
            else:
                opts.append({"value": str(o), "code": str(o)})
    elif isinstance(io, str):
        for p in re.split(r"[;\n|]", io):
            p = p.strip()
            if p:
                opts.append({"value": p, "code": p})
    return opts


def build_form_schemas(dak) -> dict[str, dict]:
    """module label -> {module, title, fields:[...]}"""
    by_module: dict[str, list[dict]] = {}
    for e in dak.elements:
        by_module.setdefault(e.get("_module"), []).append(e)

    schemas: dict[str, dict] = {}
    for module, els in by_module.items():
        parents = [e for e in els if not _OPT_RE.search(e.get("data_element_id", ""))]
        fields = []
        for el in parents:
            eid = el["data_element_id"]
            children = [c for c in els
                        if c.get("data_element_id", "").startswith(eid + ".OPT.")]
            ftype = _field_type(el)
            field = {
                "element_id": eid,
                "label": el.get("data_element_label") or eid,
                "type": ftype,
                "required": str(el.get("required")).lower() in ("true", "yes", "required", "1"),
                "help": (el.get("description_and_definition") or "")[:240],
                "fhir": el.get("fhir_resource"),
                "review_status": el.get("clinical_review_status", "not_started"),
            }
            if ftype in ("select", "boolean") or children:
                field["options"] = _options(el, children)
                if field.get("options"):
                    field["type"] = "select"
            if el.get("skip_logic"):
                field["skip_logic"] = el["skip_logic"]
            fields.append(field)
        schemas[module] = {"module": module, "title": module, "fields": fields,
                           "field_count": len(fields)}
    return schemas
