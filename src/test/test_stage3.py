"""
Stage 3 test — Retrieve.

Run from project root:
    python src/test/test_stage3.py

Tests:
    1. All 10 subsections run without error
    2. Required keys present in every result
    3. data_chunks: score in [0, 1], required fields present, count <= 8, no duplicates
    4. style_chunks: all from drhp_source when filter is set, scores in [0, 1]
    5. confidence is one of "high" / "medium" / "low" and consistent with low_confidence_flag
    6. At least 6/10 subsections are HIGH or MEDIUM confidence (plan checklist)
    7. Retrieval completes in < 30 s after index is loaded
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.dev.ingest import ingest_documents
from src.dev.embed import build_index, _load_model
from src.dev.retrieve import SUBSECTIONS, retrieve_for_subsection, retrieve_all

# ---------------------------------------------------------------------------
# Step 1: Ingest + embed (load from cache when possible)
# ---------------------------------------------------------------------------
INPUT_FILES = []
for name in ["inputs/sample_drhp.pdf", "inputs/sample_drhp.txt"]:
    if Path(name).exists():
        INPUT_FILES.append(name)
        break

if Path("inputs/company_description.txt").exists():
    INPUT_FILES.append("inputs/company_description.txt")

if Path("inputs/company_drhp.pdf").exists():
    INPUT_FILES.append("inputs/company_drhp.pdf")

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

# ---------------------------------------------------------------------------
# Step 2: Retrieve all subsections
# ---------------------------------------------------------------------------
print("=" * 60)
print("RETRIEVING ALL SUBSECTIONS")
print("=" * 60)

t0 = time.time()
results = retrieve_all(index, metadata, drhp_source=DRHP_SOURCE, model=model)
elapsed = time.time() - t0

print(f"\n[retrieve] All {len(SUBSECTIONS)} subsections done in {elapsed:.1f}s")
print()

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------
print("=" * 60)
print("RUNNING CHECKS")
print("=" * 60)

errors = []
VALID_CONFIDENCE = {"high", "medium", "low"}
REQUIRED_CHUNK_KEYS = {"chunk_id", "text", "page", "source", "score"}

# 1. Correct number of results
if len(results) != len(SUBSECTIONS):
    errors.append(f"FAIL got {len(results)} results, expected {len(SUBSECTIONS)}")

for result in results:
    name = result.get("subsection", "<unknown>")

    # 2. Required top-level keys
    for key in ("subsection", "data_chunks", "style_chunks", "confidence", "low_confidence_flag"):
        if key not in result:
            errors.append(f"FAIL [{name}] missing key '{key}'")

    conf = result.get("confidence")

    # 3. confidence is a valid value
    if conf not in VALID_CONFIDENCE:
        errors.append(f"FAIL [{name}] confidence='{conf}' not in {VALID_CONFIDENCE}")

    # 4. low_confidence_flag matches confidence
    expected_flag = conf == "low"
    if result.get("low_confidence_flag") != expected_flag:
        errors.append(
            f"FAIL [{name}] low_confidence_flag={result.get('low_confidence_flag')} "
            f"but confidence='{conf}'"
        )

    # 5. data_chunks checks
    dc = result.get("data_chunks", [])
    if not dc:
        errors.append(f"FAIL [{name}] data_chunks is empty")
    else:
        if len(dc) > 8:
            errors.append(f"FAIL [{name}] data_chunks len={len(dc)} > 8")

        # No duplicate chunk_ids
        ids = [c["chunk_id"] for c in dc]
        if len(ids) != len(set(ids)):
            errors.append(f"FAIL [{name}] duplicate chunk_ids in data_chunks")

        for i, chunk in enumerate(dc):
            missing = REQUIRED_CHUNK_KEYS - set(chunk.keys())
            if missing:
                errors.append(f"FAIL [{name}] data_chunks[{i}] missing keys {missing}")
            s = chunk.get("score", -1)
            if not (0.0 <= s <= 1.0):
                errors.append(f"FAIL [{name}] data_chunks[{i}] score={s} not in [0,1]")
            # CRITICAL: reference DRHP must never appear in data_chunks
            if chunk.get("source") == DRHP_SOURCE:
                errors.append(
                    f"FAIL [{name}] data_chunks[{i}] source='{DRHP_SOURCE}' — "
                    f"reference DRHP must not be a data source (style only)"
                )

    # 6. style_chunks: all from drhp_source, scores in [0, 1]
    sc = result.get("style_chunks", [])
    for i, chunk in enumerate(sc):
        if chunk.get("source") != DRHP_SOURCE:
            errors.append(
                f"FAIL [{name}] style_chunks[{i}] source='{chunk.get('source')}' "
                f"!= '{DRHP_SOURCE}'"
            )
        s = chunk.get("score", -1)
        if not (0.0 <= s <= 1.0):
            errors.append(f"FAIL [{name}] style_chunks[{i}] score={s} not in [0,1]")

# 7. Reference DRHP isolation — no data_chunks from drhp_source across all subsections
drhp_leaks = [
    f"{r['subsection']}: chunk {c['chunk_id']}"
    for r in results
    for c in r["data_chunks"]
    if c.get("source") == DRHP_SOURCE
]
if drhp_leaks:
    errors.append(
        f"FAIL reference DRHP '{DRHP_SOURCE}' found in data_chunks "
        f"({len(drhp_leaks)} leak(s)): {drhp_leaks[:3]}"
    )
else:
    print(f"✓  reference DRHP '{DRHP_SOURCE}' is isolated to style_chunks only")

# 8. Timing
if elapsed > 30:
    errors.append(f"FAIL retrieval took {elapsed:.1f}s, expected < 30s")
else:
    print(f"✓  retrieval time {elapsed:.1f}s < 30s")

# 8. At least 6/10 subsections HIGH or MEDIUM (plan checklist)
high_or_medium = sum(1 for r in results if r["confidence"] in ("high", "medium"))
if high_or_medium < 6:
    errors.append(
        f"FAIL only {high_or_medium}/10 subsections are HIGH or MEDIUM confidence (need >= 6)"
    )
else:
    print(f"✓  {high_or_medium}/10 subsections are HIGH or MEDIUM confidence")

# ---------------------------------------------------------------------------
# Per-subsection summary
# ---------------------------------------------------------------------------
print()
print("Per-subsection results:")
print(f"  {'CONF':8s}  {'SCORE':6s}  {'DATA':5s}  {'STYLE':5s}  SUBSECTION")
for result in results:
    top   = result["data_chunks"][0]["score"] if result["data_chunks"] else 0.0
    ndata = len(result["data_chunks"])
    nstyle = len(result["style_chunks"])
    flag  = " ⚠" if result["low_confidence_flag"] else ""
    print(
        f"  {result['confidence']:8s}  {top:.3f}  {ndata:5d}  {nstyle:5d}  "
        f"{result['subsection']}{flag}"
    )

# ---------------------------------------------------------------------------
# Spot-check: Corporate History
# ---------------------------------------------------------------------------
print()
print("Spot-check: Corporate History & Background")
corp = next(r for r in results if r["subsection"] == "Corporate History & Background")
print(f"  data_chunks : {len(corp['data_chunks'])}")
print(f"  style_chunks: {len(corp['style_chunks'])}")
if corp["data_chunks"]:
    top = corp["data_chunks"][0]
    print(f"  top chunk   : score={top['score']:.3f}  page={top['page']}  source={top['source']}")
    print(f"  text preview: {top['text'][:250]!r}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("=" * 60)
if errors:
    print("STAGE 3 FAILED")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("Stage 3 PASSED")
