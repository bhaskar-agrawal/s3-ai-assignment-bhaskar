"""
Stage 2 test — Embed & Index.

Run from project root:
    python src/test/test_stage2.py

Tests:
    1. Model loads correctly
    2. All chunks are embedded (index.ntotal == len(chunks))
    3. Embedding dimension is 384
    4. Vectors are L2-normalised (norms ~1.0) — required for cosine similarity via IndexFlatIP
    5. Cache is written and reloads correctly
    6. A sample search returns scores in [0, 1] range
"""

import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.dev.ingest import ingest_documents, print_chunk_stats
from src.dev.embed import build_index, search, EMBEDDING_DIM, INDEX_PATH, METADATA_PATH

# ---------------------------------------------------------------------------
# Step 1: Ingest (reuse Stage 1)
# ---------------------------------------------------------------------------
INPUT_FILES = []
for name in ["inputs/sample_drhp.pdf", "inputs/sample_drhp.txt"]:
    if Path(name).exists():
        INPUT_FILES.append(name)
        break

if Path("inputs/company_description.txt").exists():
    INPUT_FILES.append("inputs/company_description.txt")

if not INPUT_FILES:
    print("ERROR: No input file found. Run: python create_sample_input.py")
    sys.exit(1)

print(f"Ingesting: {INPUT_FILES}")
chunks, tables = ingest_documents(INPUT_FILES)
print_chunk_stats(chunks, tables)
print()

# ---------------------------------------------------------------------------
# Step 2: Build index (force rebuild so we always test fresh)
# ---------------------------------------------------------------------------
print("=" * 60)
print("BUILDING INDEX (force_rebuild=True — always fresh in tests)")
print("=" * 60)
index, metadata = build_index(chunks, source_files=INPUT_FILES, force_rebuild=True)

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("RUNNING CHECKS")
print("=" * 60)

errors = []

# Check 1: vector count matches chunk count
if index.ntotal != len(chunks):
    errors.append(f"FAIL index.ntotal={index.ntotal} != len(chunks)={len(chunks)}")
else:
    print(f"✓  index.ntotal == len(chunks) == {index.ntotal}")

# Check 2: embedding dimension
if index.d != EMBEDDING_DIM:
    errors.append(f"FAIL index.d={index.d}, expected {EMBEDDING_DIM}")
else:
    print(f"✓  embedding dim == {index.d}")

# Check 3: L2 norms ≈ 1.0 (required for cosine similarity via IndexFlatIP)
import faiss
sample_vecs = np.zeros((min(10, index.ntotal), EMBEDDING_DIM), dtype="float32")
for i in range(len(sample_vecs)):
    index.reconstruct(i, sample_vecs[i])
norms = np.linalg.norm(sample_vecs, axis=1)
if not np.allclose(norms, 1.0, atol=1e-2):
    errors.append(f"FAIL vectors not unit-normalised: norms={norms}")
else:
    print(f"✓  L2 norms ≈ 1.0 (mean={norms.mean():.4f}) — cosine similarity valid")

# Check 4: cache files exist
if not INDEX_PATH.exists():
    errors.append(f"FAIL cache index not found at {INDEX_PATH}")
else:
    print(f"✓  cache index saved: {INDEX_PATH}")

if not METADATA_PATH.exists():
    errors.append(f"FAIL cache metadata not found at {METADATA_PATH}")
else:
    print(f"✓  cache metadata saved: {METADATA_PATH}")

# Check 5: cache reload
print()
print("Testing cache reload ...")
from src.dev.embed import build_index as _build
index2, meta2 = _build(chunks, source_files=INPUT_FILES, force_rebuild=False)
if index2.ntotal != index.ntotal:
    errors.append(f"FAIL reloaded index has {index2.ntotal} vectors, expected {index.ntotal}")
else:
    print(f"✓  cache reloads correctly ({index2.ntotal} vectors)")

# Check 6: search scores in [0, 1]
print()
print("Testing search ...")
from src.dev.embed import _load_model
model = _load_model()

test_queries = [
    "company incorporation date CIN registered office",
    "revenue profit EBITDA financial highlights",
    "promoter background experience management",
]
all_scores_valid = True
for q in test_queries:
    results = search(q, index, metadata, top_k=5, model=model)
    if not results:
        errors.append(f"FAIL: no results for query: {q}")
        all_scores_valid = False
        continue
    top = results[0]
    if not (0.0 <= top["score"] <= 1.0):
        errors.append(f"FAIL score out of range: {top['score']} for query: {q}")
        all_scores_valid = False
    else:
        print(f"✓  '{q[:40]}...'  → top score={top['score']:.3f}  page={top['page']}")

if all_scores_valid:
    print("✓  all search scores in [0, 1] — IndexFlatIP + normalisation working")

# ---------------------------------------------------------------------------
# Source-filtered search (style chunks from DRHP only)
# ---------------------------------------------------------------------------
print()
print("Testing source-filtered search (DRHP style reference) ...")
drhp_source = Path(INPUT_FILES[0]).name
style_results = search(
    "business overview company history",
    index, metadata,
    top_k=3,
    source_filter=drhp_source,
    model=model,
)
if style_results:
    print(f"✓  source filter works — {len(style_results)} results from '{drhp_source}'")
    for r in style_results:
        print(f"     score={r['score']:.3f}  page={r['page']}  chunk={r['chunk_id']}")
else:
    errors.append("FAIL: source-filtered search returned no results")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("=" * 60)
if errors:
    print("STAGE 2 FAILED")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("Stage 2 PASSED")
