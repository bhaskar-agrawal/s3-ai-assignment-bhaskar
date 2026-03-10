# DRHP Drafting Agent — High Level Design Document

## Purpose of This Document

This document is a complete technical design specification for an AI agent that automates the drafting of one section of a Draft Red Herring Prospectus (DRHP). It is intended to be used as a system prompt or context document fed into a local LLM to assist with implementation, code generation, and decision-making during development.

When using this document with a local LLM, instruct it as follows:
> "You are a coding assistant helping build a DRHP Drafting Agent. The full system design is below. Help me implement each stage as described. Follow the package choices, architecture, and design decisions exactly as specified. Do not suggest alternatives unless explicitly asked."

---

## Background & Problem Statement

### What is a DRHP?

A Draft Red Herring Prospectus (DRHP) is a mandatory public filing document submitted to SEBI (Securities and Exchange Board of India) by companies seeking to list on Indian stock exchanges (NSE/BSE) via an IPO. It is a legally structured document that contains:

- Structured disclosures about the company
- Financial tables and summaries
- Factual descriptions of business, operations, promoters
- Risk factors
- Capital structure and shareholding patterns
- Objects of the issue (use of proceeds)
- Related party transactions
- Group company details

DRHPs are typically **200 to 500+ pages** long. They are currently written **manually** by investment bankers, lawyers, and company secretaries. The language is highly formal, repetitive by design, uses defined legal terms in ALL CAPS, avoids marketing language, and follows a strict disclosure format mandated by SEBI.

### The Assignment

Build an AI agent that:
1. Accepts a real DRHP PDF as input (for style and structure reference)
2. Accepts supporting documents (financials, ROC filings, company description, shareholding tables)
3. Produces a complete draft of **one DRHP section** that looks and reads like a real DRHP
4. Clearly marks which parts were auto-filled, which need human review, and which data is missing
5. Outputs intermediate structured data showing how raw inputs became final text

The submission must be **runnable**. Evaluators will feed documents in and expect to see real output.

---

## Section Choice: Business Overview

### Why Business Overview

Out of the five candidate sections (Capital Structure, Objects of Issue, Business Overview, Risk Factors, Group Companies), **Business Overview** is selected for the following reasons:

1. **Self-contained** — does not heavily depend on data from other sections being drafted simultaneously
2. **Fact-heavy** — relies on verifiable facts from documents, not legal judgment
3. **Clear subsection structure** — every DRHP Business Overview has the same predictable subsections
4. **Rich source mapping** — supporting documents (ROC filing, financials, company description) map directly to subsections
5. **Style is learnable** — the register is formal but consistent, making style cloning via few-shot prompting reliable
6. **Evaluator familiarity** — evaluators reading a DRHP will immediately recognize a good Business Overview

### Why NOT the other sections

- **Capital Structure** — requires precise table extraction from shareholding documents; highly error-prone with messy inputs
- **Objects of Issue** — short section but requires financial modeling context and legal judgment on use of proceeds
- **Risk Factors** — requires legal drafting judgment; hard to automate well without producing generic risks
- **Group Companies** — dependent on accurate ROC data which is often incomplete or inconsistent

---

## Core Technical Challenges & How They Are Solved

### Challenge 1: DRHP is 200-500 pages — cannot fit in LLM context

**Solution:** Chunked Retrieval (RAG)
- Split the entire DRHP into overlapping text chunks of ~400 tokens each
- Embed all chunks using a local embedding model
- For each Business Overview subsection, retrieve only the top 5-8 most relevant chunks via semantic search
- Each LLM drafting call receives only ~3,000-5,000 tokens of relevant context, not the full document

### Challenge 2: LLM cannot write 30 pages in one call reliably

**Solution:** Subsection decomposition
- Business Overview is split into ~10 discrete subsections
- Each subsection is drafted in a separate LLM API call
- Each call targets ~400-600 words of output
- All subsection outputs are stitched together in sequence
- Total output: ~12-15 pages of DRHP prose — realistic and high quality throughout

### Challenge 3: Facts are scattered across the entire DRHP and supporting docs

**Solution:** Two-pass retrieval with targeted queries
- Each subsection has a predefined semantic query designed to pull relevant chunks
- Retrieval runs against both the input DRHP AND supporting documents simultaneously
- Supporting documents (financials, ROC filings) are chunked and embedded the same way
- Low similarity scores on retrieval automatically flag a subsection for human review

### Challenge 4: Output must feel like a real DRHP, not an AI summary

**Solution:** Style cloning via few-shot prompting
- The input DRHP is not just a data source — it is a style reference
- For each subsection, the corresponding subsection from the input DRHP is retrieved and included in the LLM prompt as a style example
- The LLM is explicitly instructed to match tone, register, sentence structure, and use of defined terms
- The prompt prohibits marketing language, first-person language, and qualitative superlatives

### Challenge 5: Automation boundary must be clearly visible

**Solution:** Inline markers + separate extraction log
- Every auto-filled fact in the draft is tagged: `[AUTO: source=page_47, confidence=high]`
- Every missing fact is tagged: `[MISSING — HUMAN REVIEW REQUIRED]`
- A companion `extraction_log.json` maps every fact to its source chunk and page number
- A `review_notes.txt` consolidates all flagged items for the human reviewer

---

## System Architecture

### Pipeline Overview

```
┌─────────────────────────────────────────┐
│              INPUT LAYER                │
│  - Input DRHP PDF (style + data source) │
│  - Financial statements PDF             │
│  - ROC filing / company description     │
│  - Shareholding table (PDF or text)     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         STAGE 1: INGEST & PARSE         │
│  - Extract text with page numbers       │
│  - Extract tables separately            │
│  - Chunk into ~400 token segments       │
│  - Tag each chunk with metadata         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│       STAGE 2: EMBED & INDEX            │
│  - Embed all chunks locally             │
│  - Build FAISS index (IndexFlatIP)      │
│  - Store chunk metadata alongside       │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│     STAGE 3: RETRIEVE (per subsection)  │
│  - Run targeted query per subsection    │
│  - Retrieve top-k chunks                │
│  - Score confidence, flag low scores    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│    STAGE 4: EXTRACT & STRUCTURE         │
│  - LLM call: chunks → JSON facts        │
│  - Validate against expected schema     │
│  - Record source page per fact          │
│  - Mark missing fields                  │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│       STAGE 5: DRAFT (per subsection)   │
│  - LLM call: JSON facts + style ref     │
│  - Output: DRHP prose with markers      │
│  - ~400-600 words per subsection        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│           OUTPUT LAYER                  │
│  - business_overview_draft.txt          │
│  - extraction_log.json                  │
│  - review_notes.txt                     │
└─────────────────────────────────────────┘
```

---

## Stage-by-Stage Specification

---

### Stage 1: Ingest & Parse

#### Responsibility
Convert all raw input files (PDFs, text files) into structured text with metadata. Extract tables separately. Produce text chunks ready for embedding.

#### Input
- `inputs/sample_drhp.pdf` — the reference DRHP (200-500 pages)
- `inputs/financials.pdf` — financial statements
- `inputs/roc_filing.pdf` or `inputs/company_description.txt`
- Any additional supporting documents

#### Processing Steps

**Step 1.1 — PDF Text Extraction**

Use `pdfplumber` as the primary extractor. For each page:
- Extract raw text
- Attach page number and source filename as metadata
- Store as list of `{"text": str, "page": int, "source": str}`

Use `pymupdf (fitz)` as fallback if pdfplumber fails on a page (common with scanned PDFs or complex layouts).

**Step 1.2 — Table Extraction**

Use `pdfplumber`'s built-in table detection:
- Detect and extract all tables from all PDFs
- Convert to `pandas` DataFrames
- Store separately as `{"table": DataFrame, "page": int, "source": str}`
- Tables will be referenced directly in Stage 4 extraction for financial data

**Step 1.3 — Text Chunking**

Split extracted text into overlapping chunks:
- Target chunk size: **400 tokens** (measured with `tiktoken`, model `cl100k_base`)
- Overlap: **50 tokens** between consecutive chunks (prevents facts at boundaries being lost)
- Each chunk stores: `{"chunk_id": str, "text": str, "page": int, "source": str, "token_count": int}`

**Step 1.4 — Section Header Detection**

Run a lightweight regex pass over the DRHP text to detect major section headers:
- Pattern: lines in ALL CAPS, or lines matching known DRHP section names
- Tag chunks with their nearest detected section header
- This helps retrieve style reference chunks from the correct section later

**Caveat:** DRHP PDFs use ALL CAPS extensively in tables, footnotes, and cell headers — not just section headings. This regex will be noisy. The section tag is only used as a soft filter when retrieving style reference chunks (Step 3.3); it is not used for data retrieval, so false positives degrade style quality slightly but do not affect factual accuracy. If noise is high, disable section tagging and rely purely on semantic similarity for style chunk selection.

#### Output
- `chunks: List[Dict]` — all text chunks with metadata from all input documents
- `tables: List[Dict]` — all extracted tables with metadata

#### Packages
```
pdfplumber==0.10.3
pymupdf==1.23.8
tiktoken==0.5.2
pandas==2.1.4
```

#### Error Handling
- If a PDF page fails extraction entirely, log the page number and continue
- If a PDF appears to be scanned (low text yield per page), warn the user — see Scanned PDF Warning in the Running section
- Minimum viable: if text extraction yields less than 100 characters per page on average, flag as potentially scanned

---

### Stage 2: Embed & Index

#### Responsibility
Convert all text chunks into vector embeddings and build a searchable index for semantic retrieval.

#### Processing Steps

**Step 2.1 — Embedding Model Loading**

Load `sentence-transformers` model `all-MiniLM-L6-v2` locally:
- 22M parameter model, ~80MB download
- Runs on CPU without GPU
- Embedding dimension: 384
- Good quality for domain-specific retrieval at this scale

Do NOT use OpenAI embeddings — keeps cost at zero and removes API dependency for this stage.

**Step 2.2 — Batch Embedding**

Embed all chunks in batches of 64:
- Input: chunk texts
- Output: numpy array of shape `(num_chunks, 384)`
- Normalize embeddings to unit vectors (L2 norm = 1.0) — this makes inner product equal to cosine similarity

**Step 2.3 — FAISS Index Construction**

Build a flat inner product FAISS index:
- `faiss.IndexFlatIP(384)` for exact inner product search (equals cosine similarity for normalized vectors)
- Do NOT use `IndexFlatL2` — L2 distance and cosine similarity are numerically different, and the confidence thresholds in Stage 3 assume cosine similarity scores (higher = better match, range 0–1)
- Add all normalized chunk embeddings to the index
- Store chunk metadata list in parallel (same index order as FAISS)

**Step 2.4 — Persistence**

Save the FAISS index and metadata to disk:
- `index.faiss` — the vector index
- `chunks_metadata.json` — list of chunk dicts in index order

This allows skipping re-embedding if the same documents are used across multiple runs during testing.

#### Packages
```
sentence-transformers==2.3.1
faiss-cpu==1.7.4
numpy==1.26.2
```

#### Notes
- For a 400-page DRHP at ~250 words/page, expect ~2,500-4,000 chunks
- Embedding 4,000 chunks with MiniLM takes ~30-60 seconds on CPU
- FAISS flat index search over 4,000 vectors is instantaneous

---

### Stage 3: Retrieve

#### Responsibility
For each Business Overview subsection, retrieve the most relevant chunks from the indexed corpus. This stage determines what information the LLM sees when drafting each subsection.

#### Business Overview Subsections & Retrieval Queries

| # | Subsection Name | Primary Retrieval Query | Secondary Query |
|---|---|---|---|
| 1 | Corporate History & Background | "incorporation date founders company history establishment" | "registered office CIN company formation" |
| 2 | Nature of Business & Products | "products services offerings business segments portfolio" | "revenue segments product categories" |
| 3 | Manufacturing & Operations | "manufacturing plant facility location capacity production" | "installed capacity utilization operations" |
| 4 | Key Business Strengths | "competitive strengths key differentiators advantages" | "market position leadership strengths" |
| 5 | Promoters & Management | "promoter background experience qualification management team" | "key managerial personnel directors" |
| 6 | Subsidiaries & Associates | "subsidiaries group companies associates joint venture" | "subsidiary details incorporation ownership" |
| 7 | Financial Highlights | "revenue profit EBITDA net worth financial performance" | "total income PAT financial summary" |
| 8 | Geographic Presence | "geographic presence states regions offices branches" | "distribution network pan India presence" |
| 9 | Awards & Certifications | "awards certifications ISO accreditation recognition" | "quality certification achievements" |
| 10 | Future Strategy | "growth strategy expansion plans future outlook" | "strategic initiatives business plan" |

#### Processing Steps

**Step 3.1 — Query Embedding**
For each subsection, embed both the primary and secondary query using the same `all-MiniLM-L6-v2` model.

**Step 3.2 — Dual Query Search**
Run FAISS search for both queries, retrieve top-10 chunks each, deduplicate by chunk_id, keep top-8 by similarity score.

**Step 3.3 — Style Reference Retrieval**
Additionally retrieve chunks from the input DRHP specifically (filter by `source == "sample_drhp.pdf"`) that match the subsection query. These will be used as style examples in the drafting prompt, not as data sources.

**Step 3.4 — Confidence Scoring**

`IndexFlatIP` returns inner product scores that equal cosine similarity for normalized vectors. Scores are in the range [0, 1] — higher is a better match.

- Score > 0.65: HIGH confidence — include as primary source
- Score 0.45–0.65: MEDIUM confidence — include but flag for review
- Score < 0.45: LOW confidence — flag as potentially missing data

Note: if you use `IndexFlatL2`, distances returned are lower-is-better and do NOT map to these thresholds — this is why `IndexFlatIP` is required.

#### Output per subsection
```python
{
    "subsection": "Corporate History & Background",
    "data_chunks": [
        {"chunk_id": "chunk_047", "text": "...", "page": 12, "source": "sample_drhp.pdf", "score": 0.82},
        ...
    ],
    "style_chunks": [
        {"chunk_id": "chunk_023", "text": "...", "page": 8, "source": "sample_drhp.pdf", "score": 0.79},
        ...
    ],
    "confidence": "high",
    "low_confidence_flag": False
}
```

#### Packages
```
faiss-cpu==1.7.4
sentence-transformers==2.3.1
numpy==1.26.2
```

---

### Stage 4: Extract & Structure

#### Responsibility
Convert retrieved raw text chunks into structured JSON facts with source attribution. This is the intermediate data layer the assignment requires. Every fact is traceable to a source page.

#### Processing Steps

**Step 4.1 — Extraction Prompt Construction**

For each subsection, construct a prompt:

```
You are extracting structured facts from raw document chunks for a DRHP Business Overview section.

SUBSECTION: {subsection_name}

RAW DOCUMENT CHUNKS:
---
{chunk_1_text} [Source: {source_file}, Page: {page_number}]
---
{chunk_2_text} [Source: {source_file}, Page: {page_number}]
---
... (up to 8 chunks)

TASK:
Extract all facts relevant to the "{subsection_name}" subsection of a DRHP Business Overview.
Return ONLY a valid JSON object matching the schema below.
For every fact, record which source file and page number it came from.
If a field cannot be found in the chunks, set its value to null.
Do not invent or infer facts not explicitly present in the chunks.
Use the "other_facts" array to capture any relevant facts not covered by the predefined fields.

REQUIRED JSON SCHEMA:
{schema_for_this_subsection}
```

**Step 4.2 — Subsection-Specific JSON Schemas**

Each schema has a fixed set of known fields (which will always be checked) plus a catch-all `"other_facts"` array. This handles cases where the DRHP contains non-standard field names, or any facts not anticipated in the schema — those facts are captured in `other_facts` rather than being silently dropped.

Corporate History Schema:
```json
{
  "company_name": {"value": null, "source_page": null, "source_file": null},
  "cin": {"value": null, "source_page": null, "source_file": null},
  "incorporation_date": {"value": null, "source_page": null, "source_file": null},
  "incorporation_state": {"value": null, "source_page": null, "source_file": null},
  "registered_office_address": {"value": null, "source_page": null, "source_file": null},
  "original_business_activity": {"value": null, "source_page": null, "source_file": null},
  "key_milestones": {"value": [], "source_page": null, "source_file": null},
  "name_changes": {"value": [], "source_page": null, "source_file": null},
  "other_facts": []
}
```

`other_facts` format:
```json
[
  {"field_name": "listing_date", "value": "April 2019", "source_page": 14, "source_file": "sample_drhp.pdf"}
]
```

Financial Highlights Schema:
```json
{
  "revenue_latest_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "revenue_prior_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "revenue_two_years_ago": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "pat_latest_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "pat_prior_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "ebitda_latest_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "net_worth_latest_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "total_assets_latest_year": {"value": null, "year_label": null, "source_page": null, "source_file": null},
  "other_facts": []
}
```

Note: fields use `year_label` (e.g., "FY25", "FY2024-25") instead of hardcoded `_fy24` suffixes. This makes the schema work regardless of which fiscal year the input document covers.

**Step 4.3 — LLM API Call (Structured Output)**

Use the LLM's tool/function calling feature to guarantee valid JSON output. This eliminates the need for fragile `json.loads()` on free-text responses.

**Claude (Anthropic):**
```python
response = anthropic_client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1500,
    tools=[{
        "name": "extract_facts",
        "description": "Extract structured facts from document chunks",
        "input_schema": {"type": "object", "properties": schema_for_this_subsection}
    }],
    tool_choice={"type": "tool", "name": "extract_facts"},
    messages=[{"role": "user", "content": extraction_prompt}]
)
extracted_json = response.content[0].input
```

**OpenAI / Azure OpenAI:**
```python
response = openai_client.chat.completions.create(
    model=model_name,  # "gpt-4o-mini" or Azure deployment name
    response_format={"type": "json_object"},
    messages=[{"role": "user", "content": extraction_prompt}]
)
extracted_json = json.loads(response.choices[0].message.content)
```

**Gemini:**
```python
response = gemini_model.generate_content(
    extraction_prompt,
    generation_config={"response_mime_type": "application/json"}
)
extracted_json = json.loads(response.text)
```

In all cases, the result is a Python dict. If parsing still fails (Gemini especially can return partial JSON), retry once with an explicit format-correction instruction.

**Step 4.4 — Missing Field Detection**

After extraction, scan the JSON for null values. Each null field becomes a `[MISSING]` marker in the draft. Compile a list of all missing fields across all subsections — this becomes `review_notes.txt`.

**Step 4.5 — Extraction Log Assembly**

Aggregate all subsection JSONs into a master `extraction_log.json`:
```json
{
  "generated_at": "2024-01-15T10:30:00Z",
  "input_documents": ["sample_drhp.pdf", "financials.pdf", "company_description.txt"],
  "subsections": {
    "Corporate History & Background": { "...extracted facts..." },
    "Financial Highlights": { "...extracted facts..." }
  },
  "missing_fields_summary": [
    "Corporate History: original_business_activity",
    "Financial Highlights: ebitda_latest_year"
  ]
}
```

#### Packages
```
anthropic==0.40.0   # or openai==1.35.0 or google-generativeai==0.7.0
```

#### Cost
- ~10 extraction calls
- Average: ~800 tokens in, ~400 tokens out per call
- At claude-sonnet-4-5 pricing: approximately **$0.02 total**

---

### Stage 5: Draft

#### Responsibility
For each subsection, use the extracted JSON facts and a style reference from the input DRHP to generate a complete DRHP-quality prose draft with inline automation markers.

#### Processing Steps

**Step 5.1 — Drafting Prompt Construction**

```
You are a DRHP drafting assistant. Your task is to write one subsection of the Business Overview
section of a Draft Red Herring Prospectus (DRHP) as filed with SEBI in India.

SUBSECTION TO DRAFT: {subsection_name}

--- STYLE REFERENCE (from an actual DRHP — match this tone and structure exactly) ---
{style_chunks_text}
--- END STYLE REFERENCE ---

--- FACTS TO USE (extracted and verified from source documents) ---
{extracted_json_as_formatted_text}
--- END FACTS ---

DRAFTING INSTRUCTIONS:
1. Write in formal DRHP disclosure style — match the style reference exactly
2. Use passive voice and third person throughout ("The Company was incorporated...", "Our Company operates...")
3. Use defined terms in ALL CAPS where appropriate (e.g., "Equity Shares", "Promoters", "Subsidiaries")
4. Do NOT use marketing language, superlatives, or promotional tone
5. Do NOT invent facts not present in the FACTS section above
6. For every fact you use from the FACTS section, append the tag: [AUTO: page={page_number}]
7. For every field that was null/missing in the FACTS section, write: [MISSING — HUMAN REVIEW REQUIRED: {field_name}]
8. Target length: 400-600 words
9. Use paragraph format — no bullet points, no numbered lists

Write the subsection now:
```

**Step 5.2 — LLM API Call (Plain Text)**

Drafting does not require structured output — just free-form prose. Use whichever provider is configured (see LLM Provider Configuration).

```python
# Claude
response = anthropic_client.messages.create(
    model="claude-sonnet-4-5", max_tokens=1200,
    messages=[{"role": "user", "content": drafting_prompt}]
)
draft_text = response.content[0].text

# OpenAI / Azure OpenAI
response = openai_client.chat.completions.create(
    model=model_name, max_tokens=1200,
    messages=[{"role": "user", "content": drafting_prompt}]
)
draft_text = response.choices[0].message.content

# Gemini
response = gemini_model.generate_content(drafting_prompt)
draft_text = response.text
```

**Step 5.3 — Output Stitching**

After all 10 subsections are drafted, stitch them together with proper DRHP heading formatting:

```
SECTION: BUSINESS OVERVIEW
[auto-generated: {timestamp}]
================================================================

OUR COMPANY
-----------
[Corporate History draft]

OUR PRODUCTS AND SERVICES
--------------------------
[Products draft]

... and so on
```

**Step 5.4 — Review Notes Compilation**

Scan all drafted subsections for `[MISSING]` tags. Compile into `review_notes.txt`:

```
HUMAN REVIEW REQUIRED — DRHP Business Overview Draft
Generated: {timestamp}
Input documents: {list}

MISSING INFORMATION (requires human input before filing):
1. [Corporate History] original_business_activity — could not be found in any input document
2. [Financial Highlights] ebitda_latest_year — financial statements did not contain EBITDA breakdown
...

LOW CONFIDENCE FLAGS (verify before finalizing):
1. [Operations] installed_capacity — retrieved from page 234 with similarity score 0.51 (medium confidence)
...
```

#### Packages
```
anthropic==0.40.0   # or openai==1.35.0 or google-generativeai==0.7.0
```

#### Cost
- ~10 drafting calls
- Average: ~1,500 tokens in, ~800 tokens out per call
- At claude-sonnet-4-5 pricing: approximately **$0.04 total**

---

## Output Specification

### File 1: `business_overview_draft.txt`

Complete Business Overview section in DRHP format. Contains:
- All subsections with proper DRHP headings
- Inline `[AUTO: page=X]` markers on auto-filled facts
- Inline `[MISSING — HUMAN REVIEW REQUIRED: field_name]` markers
- Readable as a standalone document

### File 2: `extraction_log.json`

Machine-readable record of all extracted facts. Contains:
- Every fact extracted per subsection
- Source file and page number for each fact
- Null values for missing fields
- List of all missing fields across all subsections
- Retrieval confidence scores

### File 3: `review_notes.txt`

Human-readable checklist for the analyst/lawyer reviewing the draft. Contains:
- Consolidated list of all missing information
- Low confidence flags with page references
- Suggested sources to check for missing data

---

## Project Structure

```
drhp-agent/
│
├── notebook.ipynb              ← PRIMARY DELIVERABLE: end-to-end runnable notebook
├── run.py                      ← CLI entry point (argparse wrapper around the pipeline)
├── .env.example                ← Template for environment variables (copy to .env)
│
├── inputs/                     ← Place input files here
│   ├── sample_drhp.pdf         ← Reference DRHP (required)
│   ├── financials.pdf          ← Financial statements (optional)
│   ├── roc_filing.pdf          ← ROC filing (optional)
│   └── company_description.txt ← Plain text company description (optional)
│
├── outputs/                    ← Generated outputs appear here
│   ├── business_overview_draft.txt
│   ├── extraction_log.json
│   └── review_notes.txt
│
├── src/                        ← Modular source code
│   ├── __init__.py
│   ├── ingest.py               ← Stage 1: PDF parsing and chunking
│   ├── embed.py                ← Stage 2: Embedding and FAISS indexing
│   ├── retrieve.py             ← Stage 3: Semantic retrieval per subsection
│   ├── extract.py              ← Stage 4: LLM extraction to JSON
│   ├── draft.py                ← Stage 5: LLM drafting per subsection
│   ├── schemas.py              ← JSON schemas for all subsections
│   └── llm_client.py           ← LLM provider wrapper (Claude / OpenAI / Azure / Gemini)
│
├── cache/                      ← Auto-created: stores FAISS index and embeddings
│   ├── index.faiss
│   └── chunks_metadata.json
│
├── requirements.txt
└── README.md
```

---

## Requirements File

```
# requirements.txt

# PDF processing
pdfplumber==0.10.3
pymupdf==1.23.8

# Token counting
tiktoken==0.5.2

# Embeddings and vector search
sentence-transformers==2.3.1
faiss-cpu==1.7.4

# Numerical processing
numpy==1.26.2
pandas==2.1.4

# LLM APIs — install only the ones you need
anthropic==0.40.0        # Claude (Anthropic)
openai==1.35.0           # OpenAI or Azure OpenAI

# Gemini: install separately
# pip install google-generativeai==0.7.0

# Notebook
jupyter==1.0.0
ipykernel==6.27.1
```

Install with:
```bash
pip install -r requirements.txt
```

For Gemini:
```bash
pip install google-generativeai==0.7.0
```

---

## Cost Analysis

### Per Single Run (one complete Business Overview draft)

| Stage | LLM Calls | Avg Tokens In | Avg Tokens Out | Approx Cost |
|---|---|---|---|---|
| Stage 4: Extraction | 10 | 800 | 400 | ~$0.018 |
| Stage 5: Drafting | 10 | 1,500 | 800 | ~$0.042 |
| **Total per run** | **20** | — | — | **~$0.06** |

Embedding (Stage 2) — **$0.00** (local model)
PDF parsing (Stage 1) — **$0.00** (local processing)

### Testing & Experimentation Budget

| Activity | Runs | Cost |
|---|---|---|
| Initial development and debugging | 15 | ~$0.90 |
| Prompt tuning (extraction prompts) | 10 | ~$0.60 |
| Prompt tuning (drafting prompts) | 10 | ~$0.60 |
| Testing with different input DRHPs | 5 | ~$0.30 |
| Final validation runs | 5 | ~$0.30 |
| **Total experimentation budget** | **~45 runs** | **~$2.70** |

**Recommended API credit to load: $5.00** — comfortably covers all development and testing.

### Model Selection Rationale

The agent supports multiple LLM providers (see LLM Provider Configuration below). Default recommendation per provider:

| Provider | Recommended Model | Notes |
|---|---|---|
| Anthropic (Claude) | `claude-sonnet-4-5` | Best balance of quality and cost for this task |
| OpenAI | `gpt-4o-mini` | Cheaper than gpt-4o, sufficient for structured extraction |
| Azure OpenAI | Your `gpt-4o` or `gpt-4o-mini` deployment | Same as OpenAI but served from your Azure instance |
| Google Gemini | `gemini-1.5-flash` | Fast and cheap, good JSON output via `response_mime_type` |

Do NOT use the largest/most expensive model (Claude Opus, GPT-4o for all calls) — overkill for structured extraction and 5–10x more expensive.

---

## What Is Automated vs Not Automated

### Fully Automated

| Task | Method |
|---|---|
| PDF text extraction | pdfplumber / pymupdf |
| Text chunking and indexing | tiktoken + FAISS |
| Semantic retrieval of relevant content | sentence-transformers |
| Fact extraction into structured JSON | LLM API (tool_use / json_mode) |
| DRHP prose generation | LLM API |
| Source attribution and page tracking | Metadata in chunk pipeline |
| Missing field detection | Null checks on extracted JSON |
| Review notes generation | Automated scan of [MISSING] tags |

### Not Automated (Requires Human Review)

| Task | Reason |
|---|---|
| Legal accuracy verification | Requires legal domain expertise |
| Conflicting facts resolution | Two documents may state different numbers |
| Judgment calls on materiality | What to include/exclude is a legal judgment |
| Cross-section consistency | References to other sections need human check |
| Final language sign-off | Lawyers must approve wording before filing |
| Scanned PDF handling | OCR quality may be insufficient for precise numbers |

---

## DRHP Language & Style Guide (for Prompt Engineering)

This section describes the specific linguistic characteristics of DRHP prose that must be enforced in all drafting prompts.

### Register Characteristics
- Formal, legalistic, disclosure-oriented
- Passive voice preferred: "The Company was incorporated" not "We incorporated the Company"
- Third person with "Our Company" or "the Company" as the subject
- No marketing language: never use words like "leading", "best-in-class", "innovative", "state-of-the-art" unless directly quoting a certification
- Numbers always in Indian format: ₹ symbol, lakhs/crores notation (e.g., "₹ 45.32 crores")
- Dates in full format: "March 31, 2024" not "31/03/24"

### Defined Terms Convention
DRHP uses ALL CAPS for defined terms that appear in the Definitions section:
- "Equity Shares" not "shares"
- "Promoters" not "founders" or "promoter group"
- "Subsidiaries" with capital S
- "Red Herring Prospectus" or "Prospectus"
- "SEBI" always abbreviated

### Typical Sentence Patterns
- "Our Company was originally incorporated as [name] under the Companies Act, [year] on [date] at [state]..."
- "For further details, see '[Section Name]' on page [X] of this Red Herring Prospectus."
- "The following table sets forth..."
- "As of the date of this Red Herring Prospectus..."
- "For the Fiscal Year ended March 31, [year]..."

---

## Failure Modes & Mitigations

| Failure Mode | Detection | Mitigation |
|---|---|---|
| Scanned PDF with no text | Text yield < 100 chars/page | Warn user; scanned PDFs not supported — user must pre-process with external OCR |
| LLM returns invalid JSON | JSON parse exception | Tool_use/json_mode should prevent this; retry once with format-fix instruction as fallback |
| No relevant chunks found for subsection | All similarity scores < 0.40 | Mark entire subsection as [MISSING] |
| Financial figures inconsistent across docs | Two different values for same field | Flag both values in extraction log, mark for human review |
| LLM invents facts | Fact not in source chunks | Prompt explicitly prohibits this; reviewer must cross-check [AUTO] tags |
| Very short DRHP input (SME) | < 50 pages | Reduce chunk size to 200 tokens, reduce retrieval k to 3 |

---

## LLM Provider Configuration

The agent uses a single `LLMClient` wrapper in `src/llm_client.py` that normalises calls across providers. The active provider is controlled by environment variables — no code changes needed to switch providers.

```
# .env (copy from .env.example)

# Set ONE of the following:
LLM_PROVIDER=anthropic          # or: openai, azure, gemini

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini        # optional, default: gpt-4o-mini

# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o  # your deployment name
AZURE_OPENAI_API_VERSION=2024-02-01

# Gemini
GOOGLE_API_KEY=...
GEMINI_MODEL=gemini-1.5-flash   # optional, default: gemini-1.5-flash
```

### `src/llm_client.py` interface

The wrapper exposes two methods used throughout the pipeline:

```python
class LLMClient:
    def extract(self, prompt: str, schema: dict) -> dict:
        """Structured extraction — uses tool_use / json_mode / response_mime_type"""
        ...

    def draft(self, prompt: str) -> str:
        """Free-text drafting — plain completion"""
        ...
```

Both `extract.py` (Stage 4) and `draft.py` (Stage 5) import only `LLMClient` — they have no provider-specific code.

---

## Running the Agent

### Setup
```bash
git clone <repo>
cd drhp-agent
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set your LLM_PROVIDER + API key
```

### Place inputs
```bash
cp your_drhp.pdf inputs/sample_drhp.pdf
cp your_financials.pdf inputs/financials.pdf  # optional
```

### Run via CLI
```bash
python run.py \
  --drhp inputs/sample_drhp.pdf \
  --financials inputs/financials.pdf \
  --output outputs/
```

All arguments have defaults pointing to the `inputs/` directory, so a bare `python run.py` works if files are placed in the standard locations.

### Run via Notebook
```bash
jupyter notebook notebook.ipynb
# Run all cells top to bottom
# Outputs appear in outputs/ directory
```

### Scanned PDF Warning

If your DRHP is a scanned image PDF (common for older filings), text extraction will yield near-zero text. The agent will warn you:
```
WARNING: sample_drhp.pdf yields < 100 chars/page on average. This PDF may be scanned.
OCR is not supported in this version. Please provide a text-based PDF.
```
The pipeline will continue with whatever text was extracted but output quality will be poor. For scanned PDFs, use an external OCR tool (Adobe Acrobat, AWS Textract, or Google Document AI) to produce a searchable PDF before running the agent.

### Expected runtime
- Stage 1 (parsing 400-page PDF): 2-4 minutes
- Stage 2 (embedding ~4,000 chunks): 1-2 minutes
- Stages 3-5 (retrieval + 20 LLM calls): 3-5 minutes
- **Total: ~10 minutes end to end**

---

## Testing Guide — Per Stage

This section tells you what to download, what to run, and what to check to validate each stage independently before running the full pipeline.

---

### Where to Get Test Documents

**Real DRHP PDFs (free, public):**
- SEBI website: search "DRHP filed" on the SEBI DRHP filings page
- Any DRHP listed there is a real, public filing. Search for recent SME DRHPs (shorter, 80–150 pages) for faster testing.
- Good first target: find a DRHP for a manufacturing or IT services company — they have clean Business Overview sections

**Supporting documents for the target company:**
- **MCA21 portal (mca.gov.in)** → Company Search → download AOC-4 (financial statements) and MGT-7 (annual return)
- **BSE (bseindia.com)** → Corporates → Annual Reports → download the company's annual report PDF
- **Shareholding Pattern** → bseindia.com → Corporates → Shareholding Pattern (quarterly filings)
- **company_description.txt** → write 3–5 sentences from the company's website About page

**Quick smoke test option:** Use one DRHP as BOTH `sample_drhp.pdf` AND `financials.pdf`. The agent will draft the Business Overview using its own content as source — output will paraphrase the original, which is a good way to validate extraction + style cloning before moving to a fresh company.

---

### Stage 1: Ingest & Parse

**What to test:**
```python
from src.ingest import ingest_documents

chunks, tables = ingest_documents(["inputs/sample_drhp.pdf"])

print(f"Total chunks: {len(chunks)}")
print(f"Total tables: {len(tables)}")
print(f"Avg chars per chunk: {sum(len(c['text']) for c in chunks) / len(chunks):.0f}")
print(f"\nFirst chunk:\n{chunks[0]}")
print(f"\nFirst table:\n{tables[0]['table'].head()}")
```

**What to look for:**
- `Total chunks` should be 1,500–5,000 for a typical DRHP. If it's under 100, text extraction failed (likely scanned PDF).
- `Avg chars per chunk` should be ~1,500–2,000 (roughly 400 tokens at ~4 chars/token).
- Each chunk should have `page`, `source`, `chunk_id` fields.

**Verify chunk quality:**
```python
import random
for c in random.sample(chunks, 3):
    print(f"--- chunk_id={c['chunk_id']} page={c['page']} ---")
    print(c['text'][:300])
    print()
```

---

### Stage 2: Embed & Index

**What to test:**
```python
from src.embed import build_index

index, metadata = build_index(chunks)

print(f"Index size: {index.ntotal} vectors")
print(f"Embedding dimension: {index.d}")
```

**What to look for:**
- `index.ntotal` should equal `len(chunks)` exactly.
- `index.d` should be 384.
- The `cache/` directory should have `index.faiss` and `chunks_metadata.json` after this runs.
- Second run should load from cache and complete in ~1 second.

**Verify normalization (ensures cosine scores are in 0–1 range):**
```python
import numpy as np

vec = np.zeros((1, 384), dtype='float32')
index.reconstruct(0, vec[0])
print(f"L2 norm of first vector: {np.linalg.norm(vec):.4f}")  # should be ~1.0
```

---

### Stage 3: Retrieve

**What to test:**
```python
from src.retrieve import retrieve_for_subsection

result = retrieve_for_subsection(
    subsection_name="Corporate History & Background",
    index=index,
    metadata=metadata
)

print(f"Data chunks retrieved: {len(result['data_chunks'])}")
print(f"Confidence: {result['confidence']}")
print(f"\nTop data chunk (score={result['data_chunks'][0]['score']:.3f}):")
print(result['data_chunks'][0]['text'][:400])
```

**What to look for:**
- Top chunk score should be > 0.5 for a relevant subsection.
- Scores should be in [0, 1] range — if you see scores > 1.0 or negative, the index was built with `IndexFlatL2` instead of `IndexFlatIP`.

**Quick all-subsections sweep (run before spending LLM credits):**
```python
from src.retrieve import SUBSECTIONS

for sub in SUBSECTIONS:
    result = retrieve_for_subsection(sub['name'], index, metadata)
    top_score = result['data_chunks'][0]['score'] if result['data_chunks'] else 0
    print(f"{sub['name']}: confidence={result['confidence']}, top_score={top_score:.3f}")
```

This shows which subsections will have [MISSING] markers before you run the LLM.

---

### Stage 4: Extract

**What to test (single subsection first):**
```python
from src.extract import extract_facts
from src.llm_client import LLMClient

client = LLMClient()  # reads LLM_PROVIDER from .env

facts = extract_facts(
    subsection_name="Corporate History & Background",
    data_chunks=result['data_chunks'],
    llm_client=client
)

import json
print(json.dumps(facts, indent=2))
```

**What to look for:**
- Fields should have real values extracted from the document.
- `source_page` should be an integer — spot-check 2–3 facts by manually looking at that page in the PDF.
- Null fields are expected and fine.
- `other_facts` should capture any extras Claude found outside the predefined fields.
- If you get a JSON parse error, verify your LLM_PROVIDER is set correctly in `.env`.

**Cost check:** After all 10 subsections, verify ~$0.02–0.03 spent on extraction in your API dashboard.

---

### Stage 5: Draft

**What to test (single subsection first):**
```python
from src.draft import draft_subsection

draft_text = draft_subsection(
    subsection_name="Corporate History & Background",
    extracted_facts=facts,
    style_chunks=result['style_chunks'],
    llm_client=client
)

print(draft_text)
```

**What to look for:**
- Text should read like a DRHP — formal, third person, no marketing language.
- Every fact should have an `[AUTO: page=X]` tag.
- Null fields from Stage 4 should appear as `[MISSING — HUMAN REVIEW REQUIRED: field_name]`.
- Length should be 400–600 words (~2,500–3,500 characters).
- Cross-check 2–3 facts against the source PDF page numbers cited.

**End-to-end smoke test:**
```bash
python run.py --drhp inputs/sample_drhp.pdf
# Then open outputs/business_overview_draft.txt
# Count [AUTO] tags vs [MISSING] tags
```

A well-functioning run on a 200-page text DRHP should have 30–60 `[AUTO]` tags and fewer than 15 `[MISSING]` tags.

---

### Full Pipeline Checklist Before Submission

- [ ] Stage 1: chunk count is > 500 for input DRHP
- [ ] Stage 2: `index.ntotal` equals chunk count; cached correctly on second run; vector norms ≈ 1.0
- [ ] Stage 3: at least 6 of 10 subsections return HIGH or MEDIUM confidence; all scores in [0, 1]
- [ ] Stage 4: extracted JSON has no hallucinated company names or invented numbers; `other_facts` populated
- [ ] Stage 5: draft text reads as DRHP prose, not as an AI summary
- [ ] `outputs/extraction_log.json` is valid JSON and can be opened
- [ ] `outputs/review_notes.txt` lists all [MISSING] items from the draft
- [ ] Full run costs < $0.10 in LLM API credits
- [ ] Full run completes in < 15 minutes on a laptop
- [ ] Switching `LLM_PROVIDER` in `.env` (e.g., from `anthropic` to `openai`) produces equivalent output without code changes

---

## Summary

This agent solves the DRHP drafting automation problem through a clean five-stage pipeline:

1. **Ingest** — parse all input documents into structured, page-tagged text chunks
2. **Embed** — index all chunks locally for fast semantic search at zero cost
3. **Retrieve** — pull only the relevant chunks for each of the 10 Business Overview subsections
4. **Extract** — convert raw chunks into verified, source-attributed JSON facts via the configured LLM
5. **Draft** — generate DRHP-style prose per subsection using facts + style cloning via the configured LLM

The agent works with Claude, OpenAI, Azure OpenAI, or Gemini — switch providers by changing a single environment variable. The output looks like a real DRHP, every fact is traceable to a source page, missing information is clearly flagged, and the automation boundary is explicit throughout. The entire system costs under $0.10 per run and can be experimented with freely for under $5 total.
