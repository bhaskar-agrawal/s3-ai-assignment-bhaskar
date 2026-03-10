# Stage 3: Retrieve — Implementation Notes

## Files
- `src/dev/retrieve.py` — main module
- `src/test/test_stage3.py` — test script (run from project root)

## What was built
For each of the 10 Business Overview subsections, runs dual-query semantic search
against the FAISS index (Stage 2) and returns:
- `data_chunks`: top-8 deduplicated chunks from all sources (for LLM drafting)
- `style_chunks`: top-3 chunks filtered to the reference DRHP (for style cloning)
- `confidence`: "high" / "medium" / "low" based on top cosine similarity score
- `low_confidence_flag`: True when confidence == "low"

## Key design decisions

### Reference DRHP isolation (critical)
- `data_chunks` **excludes** all chunks where `source == drhp_source`
- The reference DRHP is a different company's filing — its facts must never appear in the new draft
- It is used ONLY as a style reference via `style_chunks`
- The test asserts zero leaks: any `data_chunk` with `source == drhp_source` is a FAIL

### Dual-query search per subsection
- Each subsection has a `primary_query` and `secondary_query` (from plan.md)
- Both queries fetch `TOP_K_DATA * 3` candidates (extra headroom after excluding drhp_source)
- Results are merged and deduplicated by `chunk_id` — higher score wins if overlap
- Reference DRHP chunks removed, then sorted descending and trimmed to 8

### Confidence thresholds (IndexFlatIP cosine similarity)
- HIGH   > 0.65  → include as primary source
- MEDIUM 0.45–0.65 → include, flag for review
- LOW    < 0.45  → flag as potentially missing data
- These thresholds are only valid with IndexFlatIP + L2-normalized vectors

### Style reference retrieval (Step 3.3)
- Re-uses `search()` from Stage 2 with `source_filter=drhp_source`
- `drhp_source` is the basename of the DRHP file (e.g. "sample_drhp.pdf")
- Fetches 3 style chunks; empty list if `drhp_source` is None

### Model reuse in `retrieve_all()`
- Model is loaded once by `retrieve_all()` then passed to every `retrieve_for_subsection()` call
- Avoids reloading the 80MB model 10 times

## Public API
```python
# Single subsection
result = retrieve_for_subsection(
    subsection_name="Corporate History & Background",
    index=index,
    metadata=metadata,
    drhp_source="sample_drhp.pdf",  # optional
    model=model,                     # optional, loads if None
)

# All 10 subsections (loads model once)
results = retrieve_all(index, metadata, drhp_source="sample_drhp.pdf")
```

## SUBSECTIONS constant
10 dicts, each with keys: `name`, `primary_query`, `secondary_query`.
Imported by test_stage3.py and will be used by Stage 4 to iterate subsections.
