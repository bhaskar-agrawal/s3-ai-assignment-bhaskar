"""
Stage 4 test — Extract & Structure.

Run from project root:
    python src/test/test_stage4.py

Requires LLM_PROVIDER + matching API key in environment (or .env file).

Tests:
    1. LLMClient initialises with configured provider
    2. Single subsection extraction returns correct structure
    3. All schema fields present in result (null is ok, key must exist)
    4. source_page is int or null (never a string)
    5. other_facts items have required keys
    6. All 10 subsections extracted and extraction_log.json written
    7. missing_fields_summary is a list of strings
"""

import sys
import json
import os
from pathlib import Path

# Load .env if present
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split("#")[0]                   # strip inline comments
            v = v.strip().strip('"').strip("'")   # remove surrounding quotes
            os.environ.setdefault(k.strip(), v)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.dev.ingest import ingest_documents
from src.dev.embed import build_index, _load_model
from src.dev.retrieve import retrieve_all
from src.dev.schemas import get_schema, schema_names
from src.dev.extract import extract_facts, extract_all
from src.dev.llm_client import LLMClient

# ---------------------------------------------------------------------------
# Step 1: Ingest + embed + retrieve (load from cache when possible)
# ---------------------------------------------------------------------------
INPUT_FILES = []
for name in ["inputs/sample_drhp.pdf", "inputs/sample_drhp.txt"]:
    if Path(name).exists():
        INPUT_FILES.append(name)
        break

if Path("inputs/company_description.txt").exists():
    INPUT_FILES.append("inputs/company_description.txt")

# if Path("inputs/company_drhp.pdf").exists():
#     INPUT_FILES.append("inputs/company_drhp.pdf")

if not INPUT_FILES:
    print("ERROR: No input file found. Run: python create_sample_input.py")
    sys.exit(1)

DRHP_SOURCE = Path(INPUT_FILES[0]).name

print(f"Ingesting: {INPUT_FILES}")
chunks, tables = ingest_documents(INPUT_FILES)
print(f"  {len(chunks)} chunks, {len(tables)} tables")
print()

print("Building/loading FAISS index ...")
index, metadata = build_index(chunks, source_files=INPUT_FILES, force_rebuild=False)
print()

model = _load_model()
print()

print("Retrieving all subsections ...")
retrieve_results = retrieve_all(index, metadata, drhp_source=DRHP_SOURCE, model=model)
print()

# ---------------------------------------------------------------------------
# Step 2: Initialise LLM client
# ---------------------------------------------------------------------------
print("=" * 60)
print("INITIALISING LLM CLIENT")
print("=" * 60)
try:
    client = LLMClient()
except Exception as e:
    print(f"ERROR: Could not init LLMClient: {e}")
    print("Set LLM_PROVIDER and the matching API key in .env")
    sys.exit(1)
print()

# ---------------------------------------------------------------------------
# Step 3: Single subsection spot-test
# ---------------------------------------------------------------------------
print("=" * 60)
print("SPOT-TEST: Corporate History & Background")
print("=" * 60)

corp_retrieve = next(r for r in retrieve_results if r["subsection"] == "Corporate History & Background")
corp_facts = extract_facts(
    "Corporate History & Background",
    corp_retrieve["data_chunks"],
    client,
)

print()
print(json.dumps(corp_facts, indent=2, ensure_ascii=False)[:2000])
print()

# ---------------------------------------------------------------------------
# Step 4: Run all 10 subsections
# ---------------------------------------------------------------------------
print("=" * 60)
print("EXTRACTING ALL SUBSECTIONS")
print("=" * 60)

extraction_log = extract_all(
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

# Check outputs/extraction_log.json written
log_path = Path("outputs/extraction_log.json")
if not log_path.exists():
    errors.append("FAIL outputs/extraction_log.json not found")
else:
    print(f"✓  extraction_log.json written ({log_path.stat().st_size // 1024} KB)")

# Check top-level keys in log
for key in ("generated_at", "input_documents", "subsections", "missing_fields_summary"):
    if key not in extraction_log:
        errors.append(f"FAIL extraction_log missing key '{key}'")

# Check all 10 subsections present
expected_names = set(schema_names())
actual_names   = set(extraction_log.get("subsections", {}).keys())
missing_subs   = expected_names - actual_names
if missing_subs:
    errors.append(f"FAIL missing subsections in log: {missing_subs}")
else:
    print(f"✓  all {len(expected_names)} subsections present in extraction_log")

# Check missing_fields_summary is a list of strings
mfs = extraction_log.get("missing_fields_summary", None)
if not isinstance(mfs, list):
    errors.append(f"FAIL missing_fields_summary is {type(mfs)}, expected list")
elif any(not isinstance(s, str) for s in mfs):
    errors.append("FAIL missing_fields_summary contains non-string items")
else:
    print(f"✓  missing_fields_summary: {len(mfs)} missing fields across all subsections")

# Per-subsection structural checks
for sub_name, facts in extraction_log.get("subsections", {}).items():
    schema = get_schema(sub_name)

    # All schema fields must be present
    for field in schema:
        if field == "other_facts":
            continue
        if field not in facts:
            errors.append(f"FAIL [{sub_name}] schema field '{field}' missing from result")

    # source_page must be int or null (never string)
    for field, entry in facts.items():
        if field in ("other_facts", "_meta"):
            continue
        if not isinstance(entry, dict):
            continue
        sp = entry.get("source_page")
        if sp is not None and not isinstance(sp, int):
            errors.append(
                f"FAIL [{sub_name}].{field}.source_page is {type(sp).__name__} '{sp}', expected int or null"
            )

    # other_facts items must have required keys
    for i, item in enumerate(facts.get("other_facts", [])):
        if not isinstance(item, dict):
            errors.append(f"FAIL [{sub_name}] other_facts[{i}] is not a dict")
            continue
        for req in ("field_name", "value"):
            if req not in item:
                errors.append(f"FAIL [{sub_name}] other_facts[{i}] missing key '{req}'")

    # _meta must be present
    if "_meta" not in facts:
        errors.append(f"FAIL [{sub_name}] '_meta' key missing")

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
print()
print("Per-subsection extraction summary:")
print(f"  {'MISSING':8s}  {'OTHER_FACTS':11s}  SUBSECTION")
for sub_name, facts in extraction_log.get("subsections", {}).items():
    n_missing     = len(facts.get("_meta", {}).get("missing_fields", []))
    n_other       = len(facts.get("other_facts", []))
    flag          = " ⚠" if n_missing > 3 else ""
    print(f"  {n_missing:8d}  {n_other:11d}  {sub_name}{flag}")

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
print()
print("=" * 60)
if errors:
    print("STAGE 4 FAILED")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("Stage 4 PASSED")
