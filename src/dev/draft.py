"""
Stage 5: Draft

For each Business Overview subsection, generates DRHP-quality prose using:
  - Extracted facts from Stage 4 (with source attribution)
  - Style reference chunks from the reference DRHP (Stage 3 style_chunks)

Inline markers in the output:
  [AUTO: page=X]                         — every fact used, traced to source page
  [MISSING — HUMAN REVIEW REQUIRED: field] — every null/missing field

Output files (written to outputs/):
  business_overview_draft.txt  — full stitched Business Overview section
  review_notes.txt             — consolidated missing items + low-confidence flags
"""

import re
import time
import json
from pathlib import Path
from typing import List, Dict, Optional

OUTPUT_DIR = Path("outputs")

# DRHP-style heading for each subsection
_HEADINGS = {
    "Corporate History & Background":  "OUR COMPANY",
    "Nature of Business & Products":   "OUR PRODUCTS AND SERVICES",
    "Manufacturing & Operations":      "OUR MANUFACTURING AND OPERATIONS",
    "Key Business Strengths":          "OUR COMPETITIVE STRENGTHS",
    "Promoters & Management":          "OUR PROMOTERS AND MANAGEMENT",
    "Subsidiaries & Associates":       "OUR SUBSIDIARIES AND ASSOCIATES",
    "Financial Highlights":            "FINANCIAL HIGHLIGHTS",
    "Geographic Presence":             "OUR GEOGRAPHIC PRESENCE",
    "Awards & Certifications":         "AWARDS AND CERTIFICATIONS",
    "Future Strategy":                 "OUR STRATEGY",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draft_subsection(
    subsection_name: str,
    extracted_facts: dict,
    style_chunks: List[Dict],
    llm_client,
) -> str:
    """
    Draft one subsection as DRHP prose.

    Args:
        subsection_name: e.g. "Corporate History & Background"
        extracted_facts: dict from Stage 4 extract_facts()
        style_chunks:    list of style-reference chunks from Stage 3 (drhp_source only)
        llm_client:      LLMClient instance

    Returns:
        Drafted prose string with [AUTO] and [MISSING] markers.
    """
    prompt = _build_draft_prompt(subsection_name, extracted_facts, style_chunks)

    print(f"[draft] {subsection_name} ...", end=" ", flush=True)
    t0 = time.time()
    text = llm_client.draft(prompt)
    print(f"done ({time.time() - t0:.1f}s)  words={len(text.split())}", flush=True)

    return text


def draft_all(
    extraction_log: dict,
    retrieve_results: List[Dict],
    llm_client,
    input_documents: Optional[List[str]] = None,
) -> str:
    """
    Draft all subsections, stitch into a full Business Overview, write output files.

    Args:
        extraction_log:   Output of Stage 4 extract_all().
        retrieve_results: Output of Stage 3 retrieve_all() — used for style_chunks
                          and low-confidence flags.
        llm_client:       LLMClient instance.
        input_documents:  Original input file names for the review notes header.

    Returns:
        Full draft text (also written to outputs/business_overview_draft.txt).
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Build a lookup: subsection_name → retrieve result (for style_chunks + confidence)
    retrieve_map = {r["subsection"]: r for r in retrieve_results}

    subsection_drafts = {}
    for sub_name, facts in extraction_log.get("subsections", {}).items():
        retrieve_result = retrieve_map.get(sub_name, {})
        style_chunks    = retrieve_result.get("style_chunks", [])

        text = draft_subsection(sub_name, facts, style_chunks, llm_client)
        subsection_drafts[sub_name] = {
            "text":       text,
            "confidence": retrieve_result.get("confidence", "unknown"),
        }

    # Stitch into full document
    full_draft = _stitch(subsection_drafts)

    # Write draft
    draft_path = OUTPUT_DIR / "business_overview_draft.txt"
    draft_path.write_text(full_draft, encoding="utf-8")
    print(f"\n[draft] ✓ business_overview_draft.txt written ({draft_path.stat().st_size // 1024} KB)", flush=True)

    # Write review notes
    review = _build_review_notes(subsection_drafts, retrieve_results, input_documents or [])
    review_path = OUTPUT_DIR / "review_notes.txt"
    review_path.write_text(review, encoding="utf-8")
    print(f"[draft] ✓ review_notes.txt written", flush=True)

    return full_draft


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_draft_prompt(
    subsection_name: str,
    extracted_facts: dict,
    style_chunks: List[Dict],
) -> str:
    # Format style reference
    if style_chunks:
        style_text = "\n---\n".join(c["text"].strip() for c in style_chunks)
    else:
        style_text = "(No style reference available — use standard DRHP disclosure language.)"

    # Format facts as readable lines
    facts_lines = []
    for field, entry in extracted_facts.items():
        if field in ("_meta", "other_facts"):
            continue
        if not isinstance(entry, dict):
            continue
        val  = entry.get("value")
        page = entry.get("source_page")
        src  = entry.get("source_file", "")
        if val is None or val == []:
            facts_lines.append(f"[MISSING]: {field}")
        elif isinstance(val, list):
            facts_lines.append(
                f"{field}: {', '.join(str(v) for v in val)}"
                + (f" [Source: {src}, Page: {page}]" if page else "")
            )
        else:
            facts_lines.append(
                f"{field}: {val}"
                + (f" [Source: {src}, Page: {page}]" if page else "")
            )

    # Append other_facts
    for item in extracted_facts.get("other_facts", []):
        if not isinstance(item, dict):
            continue
        fn   = item.get("field_name", "fact")
        val  = item.get("value", "")
        page = item.get("source_page")
        src  = item.get("source_file", "")
        if val:
            facts_lines.append(
                f"{fn}: {val}"
                + (f" [Source: {src}, Page: {page}]" if page else "")
            )

    facts_text = "\n".join(facts_lines) if facts_lines else "(No facts extracted.)"

    return f"""You are a DRHP drafting assistant helping write one subsection of the Business Overview section of a Draft Red Herring Prospectus (DRHP) as filed with SEBI in India.

Subsection to draft: {subsection_name}

Style reference (tone and sentence structure only — facts in this section belong to a different company and should not be used):
---
{style_text}
---

Facts to use (these are the only facts that should appear in the drafted text):
---
{facts_text}
---

Drafting guidelines:

1. Factual accuracy: Only use information from the facts section above. The style reference is provided to guide tone and sentence structure, not as a source of facts. Company names, dates, numbers, and other specifics should come exclusively from the facts section.

2. Inline citations: After every sentence that uses a fact, append the citation tag immediately — before the next sentence begins. For example: "The Company was incorporated in Maharashtra [AUTO: doc=roc.pdf, page=2]. It currently operates two manufacturing facilities [AUTO: doc=desc.txt, page=1]." Use the exact filename and page number shown in the facts section.

3. Missing fields: For every field marked as [MISSING] in the facts section, include this placeholder in the prose exactly as written: [MISSING — HUMAN REVIEW REQUIRED: {{field_name}}].

4. Tone and language: Write in a formal, legalistic, and objective register consistent with SEBI filings. Avoid subjective or promotional language. Words such as "robust", "cutting-edge", "seamless", "leading", "innovative", "ecosystem", "best-in-class", and "strategic" should not appear.

5. Format: Write 400–600 words in continuous prose paragraphs. No bullet points or numbered lists. Use passive voice and third person ("The Company..."). Use defined terms in capital letters where appropriate (e.g., "Equity Shares", "Promoters", "Subsidiaries").

Please write the subsection now:"""


# ---------------------------------------------------------------------------
# Output stitching
# ---------------------------------------------------------------------------

def _stitch(subsection_drafts: dict) -> str:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    lines = [
        "SECTION: BUSINESS OVERVIEW",
        f"[auto-generated: {timestamp}]",
        "=" * 64,
        "",
    ]

    for sub_name, info in subsection_drafts.items():
        heading = _HEADINGS.get(sub_name, sub_name.upper())
        underline = "-" * len(heading)
        lines += [
            heading,
            underline,
            "",
            info["text"].strip(),
            "",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Review notes
# ---------------------------------------------------------------------------

def _build_review_notes(
    subsection_drafts: dict,
    retrieve_results: List[Dict],
    input_documents: List[str],
) -> str:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    missing_items = []
    low_conf_items = []

    # Scan drafted text for [MISSING] tags
    missing_pattern = re.compile(r"\[MISSING — HUMAN REVIEW REQUIRED: ([^\]]+)\]")
    for sub_name, info in subsection_drafts.items():
        for match in missing_pattern.finditer(info["text"]):
            missing_items.append(f"[{sub_name}] {match.group(1)}")

    # Collect low/medium confidence flags from retrieval
    for result in retrieve_results:
        conf = result.get("confidence", "unknown")
        if conf == "low":
            top_score = result["data_chunks"][0]["score"] if result["data_chunks"] else 0.0
            missing_items.append(
                f"[{result['subsection']}] entire subsection — no high-confidence source chunks found"
            )
        elif conf == "medium":
            top = result["data_chunks"][0] if result["data_chunks"] else {}
            low_conf_items.append(
                f"[{result['subsection']}] top chunk score={result['data_chunks'][0]['score']:.3f} "
                f"(medium confidence) — page {top.get('page', '?')}, source: {top.get('source', '?')}"
            )

    lines = [
        "HUMAN REVIEW REQUIRED — DRHP Business Overview Draft",
        f"Generated: {timestamp}",
        f"Input documents: {', '.join(input_documents) if input_documents else 'unknown'}",
        "",
        "=" * 64,
        "",
    ]

    if missing_items:
        lines += ["MISSING INFORMATION (requires human input before filing):"]
        for i, item in enumerate(missing_items, 1):
            lines.append(f"  {i}. {item}")
        lines.append("")
    else:
        lines += ["MISSING INFORMATION: None — all fields extracted successfully.", ""]

    if low_conf_items:
        lines += ["LOW CONFIDENCE FLAGS (verify before finalising):"]
        for i, item in enumerate(low_conf_items, 1):
            lines.append(f"  {i}. {item}")
        lines.append("")
    else:
        lines += ["LOW CONFIDENCE FLAGS: None.", ""]

    return "\n".join(lines)
