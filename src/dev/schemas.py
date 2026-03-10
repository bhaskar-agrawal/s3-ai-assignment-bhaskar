"""
Stage 4: JSON schemas for all 10 Business Overview subsections.

Schema field conventions:
  - Standard field:  {"value": null, "source_page": null, "source_file": null}
  - List field:      {"value": [],   "source_page": null, "source_file": null}
  - Financial field: {"value": null, "year_label": null, "source_page": null, "source_file": null}
  - other_facts:     [] — catch-all for facts not covered by predefined fields

other_facts item format:
  {"field_name": str, "value": str, "source_page": int|null, "source_file": str|null}
"""

import copy
from typing import Dict

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

_SCHEMAS: Dict[str, dict] = {

    "Corporate History & Background": {
        "company_name":               {"value": None, "source_page": None, "source_file": None},
        "cin":                        {"value": None, "source_page": None, "source_file": None},
        "incorporation_date":         {"value": None, "source_page": None, "source_file": None},
        "incorporation_state":        {"value": None, "source_page": None, "source_file": None},
        "registered_office_address":  {"value": None, "source_page": None, "source_file": None},
        "original_business_activity": {"value": None, "source_page": None, "source_file": None},
        "key_milestones":             {"value": [],   "source_page": None, "source_file": None},
        "name_changes":               {"value": [],   "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Nature of Business & Products": {
        "business_description":  {"value": None, "source_page": None, "source_file": None},
        "products_and_services": {"value": [],   "source_page": None, "source_file": None},
        "revenue_segments":      {"value": [],   "source_page": None, "source_file": None},
        "industry_sector":       {"value": None, "source_page": None, "source_file": None},
        "key_customers":         {"value": [],   "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Manufacturing & Operations": {
        "manufacturing_locations": {"value": [],   "source_page": None, "source_file": None},
        "installed_capacity":      {"value": None, "source_page": None, "source_file": None},
        "utilization_rate":        {"value": None, "source_page": None, "source_file": None},
        "key_raw_materials":       {"value": [],   "source_page": None, "source_file": None},
        "employees_count":         {"value": None, "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Key Business Strengths": {
        "strengths": {"value": [], "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Promoters & Management": {
        "promoters":              {"value": [],   "source_page": None, "source_file": None},
        "promoter_group_holding": {"value": None, "source_page": None, "source_file": None},
        "managing_director":      {"value": None, "source_page": None, "source_file": None},
        "key_managerial_personnel": {"value": [], "source_page": None, "source_file": None},
        "board_of_directors":     {"value": [],   "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Subsidiaries & Associates": {
        "subsidiaries":   {"value": [], "source_page": None, "source_file": None},
        "associates":     {"value": [], "source_page": None, "source_file": None},
        "joint_ventures": {"value": [], "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Financial Highlights": {
        "revenue_latest_year":     {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "revenue_prior_year":      {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "revenue_two_years_ago":   {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "pat_latest_year":         {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "pat_prior_year":          {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "ebitda_latest_year":      {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "net_worth_latest_year":   {"value": None, "year_label": None, "source_page": None, "source_file": None},
        "total_assets_latest_year":{"value": None, "year_label": None, "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Geographic Presence": {
        "states_present":                {"value": [],   "source_page": None, "source_file": None},
        "number_of_offices":             {"value": None, "source_page": None, "source_file": None},
        "international_presence":        {"value": None, "source_page": None, "source_file": None},
        "distribution_network_description": {"value": None, "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Awards & Certifications": {
        "awards":          {"value": [], "source_page": None, "source_file": None},
        "certifications":  {"value": [], "source_page": None, "source_file": None},
        "accreditations":  {"value": [], "source_page": None, "source_file": None},
        "other_facts": [],
    },

    "Future Strategy": {
        "growth_plans":          {"value": None, "source_page": None, "source_file": None},
        "expansion_targets":     {"value": [],   "source_page": None, "source_file": None},
        "strategic_initiatives": {"value": [],   "source_page": None, "source_file": None},
        "capex_plans":           {"value": None, "source_page": None, "source_file": None},
        "other_facts": [],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema(subsection_name: str) -> dict:
    """
    Return a fresh (deep-copied) schema template for the given subsection.
    Falls back to the generic schema for novel subsections detected from the DRHP.
    """
    if subsection_name not in _SCHEMAS:
        return get_generic_schema()
    return copy.deepcopy(_SCHEMAS[subsection_name])


def get_generic_schema() -> dict:
    """
    Fallback schema for subsections not in the predefined list.
    Uses only other_facts so any content the LLM finds is captured.
    """
    return {"other_facts": []}


def schema_names() -> list:
    return list(_SCHEMAS.keys())


def to_anthropic_input_schema(schema: dict) -> dict:
    """
    Convert a subsection schema dict into an Anthropic tool input_schema
    (JSON Schema format with type + properties).
    """
    properties = {}
    for field, template in schema.items():
        if field == "other_facts":
            properties[field] = {
                "type": "array",
                "description": "Any relevant facts not covered by predefined fields.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {"type": "string"},
                        "value":      {"type": "string"},
                        "source_page": {"type": ["integer", "null"]},
                        "source_file": {"type": ["string", "null"]},
                    },
                },
            }
        elif isinstance(template.get("value"), list):
            field_props = {
                "value":       {"type": "array", "items": {"type": "string"}},
                "source_page": {"type": ["integer", "null"]},
                "source_file": {"type": ["string", "null"]},
            }
            if "year_label" in template:
                field_props["year_label"] = {"type": ["string", "null"]}
            properties[field] = {"type": "object", "properties": field_props}
        else:
            field_props = {
                "value":       {"type": ["string", "null"]},
                "source_page": {"type": ["integer", "null"]},
                "source_file": {"type": ["string", "null"]},
            }
            if "year_label" in template:
                field_props["year_label"] = {"type": ["string", "null"]}
            properties[field] = {"type": "object", "properties": field_props}

    return {"type": "object", "properties": properties}
