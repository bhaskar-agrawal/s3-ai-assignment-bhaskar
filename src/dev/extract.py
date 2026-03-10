"""
Stage 4: Extract & Structure

For each Business Overview subsection, sends retrieved chunks to the LLM
and gets back a structured JSON dict of facts with source attribution.

Output files (written to outputs/):
  extraction_log.json  — all subsection facts + missing fields summary
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional

from src.dev.schemas import get_schema, schema_names

OUTPUT_DIR = Path("outputs")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_facts(
    subsection_name: str,
    data_chunks: List[Dict],
    llm_client,
) -> dict:
    """
    Extract structured facts for one subsection.

    Args:
        subsection_name: Must match a key in schemas.py.
        data_chunks:     Retrieved chunks from Stage 3 (data_chunks only — NOT style_chunks).
        llm_client:      LLMClient instance from llm_client.py.

    Returns:
        Extracted dict matching the subsection schema, with null for missing fields.
        Always includes a '_meta' key with extraction metadata.
    """
    schema = get_schema(subsection_name)
    prompt = _build_extraction_prompt(subsection_name, data_chunks, schema)

    print(f"[extract] {subsection_name} ...", end=" ", flush=True)
    t0 = time.time()
    raw = llm_client.extract(prompt, schema)
    elapsed = time.time() - t0

    # Merge LLM output into the schema template (fill missing keys with template defaults)
    result = _merge_with_schema(raw, schema)

    missing = _find_missing_fields(result)
    print(f"done ({elapsed:.1f}s)  missing={len(missing)}", flush=True)

    result["_meta"] = {
        "subsection":    subsection_name,
        "chunks_used":   len(data_chunks),
        "missing_fields": missing,
        "elapsed_s":     round(elapsed, 2),
    }
    return result


def extract_all(
    retrieve_results: List[Dict],
    llm_client,
    input_documents: Optional[List[str]] = None,
) -> dict:
    """
    Run extract_facts for all subsections and assemble the extraction log.

    Args:
        retrieve_results:  List of dicts from Stage 3 retrieve_all().
        llm_client:        LLMClient instance.
        input_documents:   Original input file names for the log header.

    Returns:
        Master extraction log dict (also written to outputs/extraction_log.json).
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    subsections_data = {}
    all_missing = []

    for result in retrieve_results:
        name       = result["subsection"]
        data_chunks = result["data_chunks"]  # reference DRHP already excluded by Stage 3

        facts = extract_facts(name, data_chunks, llm_client)
        subsections_data[name] = facts

        for field in facts.get("_meta", {}).get("missing_fields", []):
            all_missing.append(f"{name}: {field}")

    log = {
        "generated_at":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_documents":        input_documents or [],
        "subsections":            subsections_data,
        "missing_fields_summary": all_missing,
    }

    log_path = OUTPUT_DIR / "extraction_log.json"
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[extract] ✓ extraction_log.json saved ({len(all_missing)} missing fields total)", flush=True)

    return log


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_extraction_prompt(
    subsection_name: str,
    data_chunks: List[Dict],
    schema: dict,
) -> str:
    # Build chunk block
    chunk_lines = []
    for chunk in data_chunks:
        chunk_lines.append(
            f"[Source: {chunk.get('source', 'unknown')}, Page: {chunk.get('page', '?')}]\n"
            f"{chunk['text'].strip()}"
        )
    chunks_text = "\n---\n".join(chunk_lines)

    # Serialise schema template (strip _meta if present, format for readability)
    schema_display = {k: v for k, v in schema.items()}
    schema_json = json.dumps(schema_display, indent=2, ensure_ascii=False)

    return f"""You are extracting structured facts from raw document chunks for a DRHP Business Overview section.

SUBSECTION: {subsection_name}

RAW DOCUMENT CHUNKS:
---
{chunks_text}
---

TASK:
Extract all facts relevant to the "{subsection_name}" subsection of a DRHP Business Overview.
Return ONLY a valid JSON object matching the schema below.
For every fact you extract, record the source_file (filename) and source_page (integer page number) it came from.
If a field cannot be found in the chunks, set its value to null (or [] for list fields).
Do NOT invent or infer facts not explicitly present in the chunks above.
Use the "other_facts" array to capture any relevant facts not covered by the predefined fields.

REQUIRED JSON SCHEMA:
{schema_json}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_with_schema(raw: dict, schema: dict) -> dict:
    """
    Merge LLM output into the schema template.
    Missing fields are filled with template defaults (null / []).
    Extra keys from LLM are kept as-is.
    """
    merged = {}
    for field, default in schema.items():
        if field in raw:
            merged[field] = raw[field]
        else:
            merged[field] = default
    # Preserve any extra keys the LLM returned
    for field in raw:
        if field not in merged:
            merged[field] = raw[field]
    # Normalise other_facts regardless of what shape the LLM returned
    merged["other_facts"] = _normalise_other_facts(merged.get("other_facts", []))
    return merged


def _normalise_other_facts(items) -> List[Dict]:
    """
    Normalise other_facts to always be a list of dicts with at least
    'field_name' and 'value' keys, regardless of what shape the LLM returned.

    LLMs commonly return:
      - strings                        → {"field_name": "fact", "value": str}
      - dicts with arbitrary keys      → use first k/v pair or stringify
      - dicts already in correct format → keep as-is
    """
    if not isinstance(items, list):
        return []

    normalised = []
    for item in items:
        if isinstance(item, str):
            normalised.append({
                "field_name":  "additional_fact",
                "value":       item,
                "source_page": None,
                "source_file": None,
            })
        elif isinstance(item, dict):
            # Already correct format
            if "field_name" in item and "value" in item:
                normalised.append(item)
            else:
                # Dict with arbitrary keys — use key/value of first entry or stringify
                keys = [k for k in item if k not in ("source_page", "source_file")]
                if keys:
                    field = keys[0]
                    normalised.append({
                        "field_name":  field,
                        "value":       str(item[field]),
                        "source_page": item.get("source_page"),
                        "source_file": item.get("source_file"),
                    })
                else:
                    normalised.append({
                        "field_name":  "additional_fact",
                        "value":       str(item),
                        "source_page": None,
                        "source_file": None,
                    })
        else:
            # Fallback: stringify whatever came back
            normalised.append({
                "field_name":  "additional_fact",
                "value":       str(item),
                "source_page": None,
                "source_file": None,
            })
    return normalised


def _find_missing_fields(facts: dict) -> List[str]:
    """
    Return list of field names where value is null or empty list.
    Skips 'other_facts' and '_meta'.
    """
    missing = []
    for field, entry in facts.items():
        if field in ("other_facts", "_meta"):
            continue
        if not isinstance(entry, dict):
            continue
        val = entry.get("value")
        if val is None or val == []:
            missing.append(field)
    return missing
