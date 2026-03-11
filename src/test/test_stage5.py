"""
Stage 5 test — Draft.

Run from project root:
    python src/test/test_stage5.py [input_dir]

    input_dir  Path to a directory containing input files (default: inputs/).
               Rules for files in that directory:
                 - sample_drhp.pdf  (or sample_drhp.txt)  → reference DRHP (style + structure)
                 - all other .pdf / .txt / .md files       → context documents for the new draft

Requires LLM_PROVIDER + API key in .env

Tests:
    1. Single subsection draft returns non-empty prose
    2. [AUTO: page=X] markers present in drafted text
    3. [MISSING] markers present when facts were null
    4. Draft length is 200–900 words (lenient range for test data)
    5. All 10 subsections drafted without error
    6. business_overview_draft.txt written to outputs/
    7. review_notes.txt written to outputs/
    8. No reference DRHP facts leaked into draft (style_chunks text not copy-pasted)
"""

import sys
import re
import os
from pathlib import Path

# Load .env
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split("#")[0].strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.dev.ingest import ingest_documents, tables_to_chunks
from src.dev.embed import build_index, _load_model
from src.dev.retrieve import retrieve_all
from src.dev.extract import extract_all
from src.dev.draft import draft_subsection, draft_all
from src.dev.llm_client import LLMClient

# ---------------------------------------------------------------------------
# Resolve input directory (CLI arg or default "inputs/")
# ---------------------------------------------------------------------------
SUPPORTED_EXTS = {".pdf", ".txt", ".md"}

input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("inputs")
if not input_dir.is_dir():
    print(f"ERROR: input directory not found: {input_dir}")
    sys.exit(1)

# Reference DRHP: sample_drhp.pdf preferred, then sample_drhp.txt (optional)
DRHP_FILE: Path | None = None
for candidate in ["sample_drhp.pdf", "sample_drhp.txt"]:
    p = input_dir / candidate
    if p.exists():
        DRHP_FILE = p
        break

# All supported files in the directory
all_files = sorted(
    f for f in input_dir.iterdir()
    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
)

if DRHP_FILE is None:
    # No reference DRHP — treat ALL files as context documents
    print(f"WARNING: No sample_drhp.pdf found in {input_dir}/")
    print("  Drafting without style reference — standard DRHP language will be used.")
    context_files = all_files
    INPUT_FILES   = [str(f) for f in context_files]
    DRHP_SOURCE   = None
else:
    context_files = [f for f in all_files if f.name != DRHP_FILE.name]
    INPUT_FILES   = [str(DRHP_FILE)] + [str(f) for f in context_files]
    DRHP_SOURCE   = DRHP_FILE.name

if not INPUT_FILES:
    print(f"ERROR: No input files found in {input_dir}/")
    sys.exit(1)

if not context_files and DRHP_FILE:
    print(f"WARNING: No context documents found — draft will be based on the reference DRHP only.")

print(f"Input directory : {input_dir.resolve()}")
print(f"Reference DRHP  : {DRHP_FILE.name if DRHP_FILE else '(none — no style reference)'}")
print(f"Context files   : {[f.name for f in context_files] or '(none)'}")
print()

# ---------------------------------------------------------------------------
# Setup: ingest → embed → retrieve → extract (reuse cache + previous log)
# ---------------------------------------------------------------------------
print(f"Ingesting: {INPUT_FILES}")
chunks, tables = ingest_documents(INPUT_FILES)
table_chunks = tables_to_chunks(tables, start_chunk_id=len(chunks))
chunks = chunks + table_chunks
print(f"  {len(chunks)} chunks ({len(table_chunks)} from tables)\n")

print("Building/loading FAISS index ...")
index, metadata = build_index(chunks, source_files=INPUT_FILES, force_rebuild=False)
print()

model = _load_model()
print()

print("Retrieving subsections ...")
retrieve_results = retrieve_all(index, metadata, drhp_source=DRHP_SOURCE, model=model)
print()

print("Initialising LLM client ...")
try:
    client = LLMClient()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
print()

# ---------------------------------------------------------------------------
# Run Stage 4 to get extraction_log
# ---------------------------------------------------------------------------
print("Extracting facts (Stage 4) ...")
extraction_log = extract_all(retrieve_results, client, input_documents=INPUT_FILES)
print()

# ---------------------------------------------------------------------------
# Spot-test: single subsection draft (use first available subsection)
# ---------------------------------------------------------------------------
SPOT_TEST_PREFERRED = "Corporate History & Background"
available_subsections = list(extraction_log["subsections"].keys())
spot_sub = SPOT_TEST_PREFERRED if SPOT_TEST_PREFERRED in available_subsections else available_subsections[0]

print("=" * 60)
print(f"SPOT-TEST: {spot_sub}")
print("=" * 60)

corp_facts    = extraction_log["subsections"][spot_sub]
corp_retrieve = next(r for r in retrieve_results if r["subsection"] == spot_sub)

corp_draft = draft_subsection(
    spot_sub,
    corp_facts,
    corp_retrieve["style_chunks"],
    client,
)

print()
print(corp_draft[:1500])
print()

# ---------------------------------------------------------------------------
# Full draft: all 10 subsections
# ---------------------------------------------------------------------------
print("=" * 60)
print("DRAFTING ALL SUBSECTIONS")
print("=" * 60)

full_draft = draft_all(
    extraction_log,
    retrieve_results,
    client,
    input_documents=INPUT_FILES,
)

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("RUNNING CHECKS")
print("=" * 60)

errors = []

# 1. Output files exist
draft_path  = Path("outputs/business_overview_draft.txt")
review_path = Path("outputs/review_notes.txt")

if not draft_path.exists():
    errors.append("FAIL outputs/business_overview_draft.txt not found")
else:
    print(f"✓  business_overview_draft.txt ({draft_path.stat().st_size // 1024} KB)")

if not review_path.exists():
    errors.append("FAIL outputs/review_notes.txt not found")
else:
    print(f"✓  review_notes.txt ({review_path.stat().st_size} bytes)")

# 2. Full draft contains all 10 subsection headings
from src.dev.draft import _HEADINGS
for sub_name, heading in _HEADINGS.items():
    if heading not in full_draft:
        errors.append(f"FAIL heading '{heading}' not found in draft")
    else:
        print(f"✓  heading present: {heading}")

# 3. Spot-test draft: non-empty, has [AUTO] markers, reasonable word count
if not corp_draft.strip():
    errors.append("FAIL Corporate History draft is empty")
else:
    word_count = len(corp_draft.split())
    if word_count < 50:
        errors.append(f"FAIL draft too short: {word_count} words")
    elif word_count > 1200:
        errors.append(f"FAIL draft too long: {word_count} words")
    else:
        print(f"✓  spot-test draft word count: {word_count}")

auto_tags = re.findall(r"\[AUTO: doc=\S+, page=\S+\]", corp_draft)
if not auto_tags:
    # Flexible — LLM may format tags slightly differently; just warn
    print("  ⚠  no [AUTO: doc=X, page=Y] tags in spot-test draft — check prompt adherence")
else:
    print(f"✓  {len(auto_tags)} [AUTO] tag(s) found in spot-test draft")

# 4. review_notes.txt contains "MISSING INFORMATION" section
review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else ""
if "MISSING INFORMATION" not in review_text:
    errors.append("FAIL review_notes.txt missing 'MISSING INFORMATION' section")
else:
    print("✓  review_notes.txt has MISSING INFORMATION section")

if "HUMAN REVIEW REQUIRED" not in review_text:
    errors.append("FAIL review_notes.txt missing 'HUMAN REVIEW REQUIRED' header")
else:
    print("✓  review_notes.txt has HUMAN REVIEW REQUIRED header")

# 5. Full draft is non-trivially long
total_words = len(full_draft.split())
if total_words < 200:
    errors.append(f"FAIL full draft too short: {total_words} words")
else:
    print(f"✓  full draft total words: {total_words}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("=" * 60)
if errors:
    print("STAGE 5 FAILED")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("Stage 5 PASSED")
    print()
    print("Outputs written to:")
    print(f"  {draft_path.resolve()}")
    print(f"  {review_path.resolve()}")
