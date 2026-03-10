# Stage 5: Draft — Implementation Notes

## Files
- `src/dev/draft.py`       — main module
- `src/test/test_stage5.py` — test script (run from project root)
- `outputs/business_overview_draft.txt` — stitched full draft (auto-created)
- `outputs/review_notes.txt`            — missing items + low-confidence flags (auto-created)

## What was built

### draft_subsection(subsection_name, extracted_facts, style_chunks, llm_client) -> str
- Builds prompt with style reference (style_chunks text) + formatted facts
- Facts formatted as: `field: value [Source: file, Page: X]` or `[MISSING]: field`
- Calls `llm_client.draft()` (free-text, no structured output needed)
- Returns raw prose with [AUTO] and [MISSING] markers

### draft_all(extraction_log, retrieve_results, llm_client, input_documents) -> str
- Iterates all 10 subsections in extraction_log order
- Looks up style_chunks + confidence from retrieve_results
- Stitches all subsection drafts with DRHP-style headings
- Writes `outputs/business_overview_draft.txt` and `outputs/review_notes.txt`
- Returns full draft string

## Output format

### business_overview_draft.txt
```
SECTION: BUSINESS OVERVIEW
[auto-generated: 2025-...]
================================================================

OUR COMPANY
-----------
<prose with [AUTO: page=X] and [MISSING — HUMAN REVIEW REQUIRED: field] markers>

OUR PRODUCTS AND SERVICES
-------------------------
...
```

### review_notes.txt
- Header with timestamp + input documents
- MISSING INFORMATION: all [MISSING] fields found by regex scan of draft text
  + all LOW confidence subsections flagged
- LOW CONFIDENCE FLAGS: MEDIUM confidence subsections with top chunk score + page

## Subsection → DRHP heading mapping (_HEADINGS dict)
| Subsection                    | Heading                              |
|-------------------------------|--------------------------------------|
| Corporate History & Background | OUR COMPANY                         |
| Nature of Business & Products  | OUR PRODUCTS AND SERVICES           |
| Manufacturing & Operations     | OUR MANUFACTURING AND OPERATIONS    |
| Key Business Strengths         | OUR COMPETITIVE STRENGTHS           |
| Promoters & Management         | OUR PROMOTERS AND MANAGEMENT        |
| Subsidiaries & Associates      | OUR SUBSIDIARIES AND ASSOCIATES     |
| Financial Highlights           | FINANCIAL HIGHLIGHTS                |
| Geographic Presence            | OUR GEOGRAPHIC PRESENCE             |
| Awards & Certifications        | AWARDS AND CERTIFICATIONS           |
| Future Strategy                | OUR STRATEGY                        |

## Prompt design
- Explicit: "do not invent facts", "match style reference exactly"
- [AUTO: page=X] tag required after every fact sentence
- [MISSING — HUMAN REVIEW REQUIRED: field_name] for every null field
- Target 400–600 words, paragraph format, no bullet points
- Falls back to standard DRHP language if no style_chunks available

## Running
```bash
python src/test/test_stage5.py
```
Runs the full pipeline (Stages 1–5) end to end. Uses cached index if available.
