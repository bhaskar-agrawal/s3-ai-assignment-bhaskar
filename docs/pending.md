# Pending Improvements

---

## 1. Streaming Ingest + Embed (per-file, not all-at-once)

### Problem
`ingest_documents()` currently loads all input files before embedding begins.
With N files of size S each, peak RAM grows to **N × S** — and briefly **2× that** during
`build_index()` because `chunks` (Stage 1) and `metadata` (Stage 2) both exist simultaneously.

Example: 10 files × 10 MB = 100 MB raw → 400–600 MB peak Python objects in memory.

### Proposed fix
Process and embed one file at a time, discarding each file's chunks before moving to the next:

```
file_1.pdf → parse → embed → add to FAISS index → discard chunks
file_2.pdf → parse → embed → add to FAISS index → discard chunks
...
file_N.pdf → parse → embed → add to FAISS index → discard chunks
→ save index + metadata to disk
```

`IndexFlatIP.add()` supports incremental additions, so this works without changing the FAISS setup.
Peak memory stays at roughly **single-file size** regardless of how many files are passed.

### What stays unchanged
- During retrieval (Stage 3), `chunks_metadata.json` still needs to be fully loaded in memory
  because FAISS returns integer indices and the text must be looked up from metadata.
  This is irreducible with the current flat-file metadata design.
- For larger scale (50,000+ chunks), replace `chunks_metadata.json` with SQLite
  and do point lookups by index ID to avoid loading everything at once.

### Current scope verdict
Not urgent — current inputs are 1 DRHP + 2–3 supporting docs (~15–20 MB total).
Implement this before scaling to 10+ input files or files > 20 MB each.

---

## 2. ✅ Infer Business Overview Structure from Reference DRHP — IMPLEMENTED

### What was built
`detect_subsections_from_drhp(metadata, drhp_source)` in `retrieve.py`:
1. Filters chunks from `drhp_source`, sorted by page
2. Locates the chunk containing "BUSINESS OVERVIEW" or "OUR BUSINESS"
3. Scans the next 40 chunks for ALL-CAPS short lines (heading pattern regex)
4. Fuzzy-matches each heading to a known subsection via keyword overlap (`_SUBSECTION_KEYWORDS`)
   - Match found → use predefined queries + predefined schema
   - Novel heading → use heading words as queries + `get_generic_schema()` (only `other_facts`)
5. Falls back to hardcoded `SUBSECTIONS` if fewer than 3 headings detected

`retrieve_all()` now calls `detect_subsections_from_drhp()` before iterating subsections.
`retrieve_for_subsection()` accepts `_sub_dict` so novel subsections pass their queries directly.
`schemas.py` — `get_schema()` returns `get_generic_schema()` instead of raising ValueError
for unknown subsection names.

### Known limitation
The heading regex (`^[A-Z][A-Z\s&,\-\(\)\.\/\']{2,79}$`) will miss headings that start with
lowercase or are formatted with mixed case. Works well on typical DRHP PDFs where section
headings are fully capitalised.
