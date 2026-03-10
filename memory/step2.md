# Stage 2: Embed & Index — Implementation Notes

## Files
- `src/dev/embed.py` — main module
- `src/test/test_stage2.py` — test script (run from project root)
- `cache/index.faiss` — persisted FAISS index (auto-created)
- `cache/chunks_metadata.json` — chunk metadata in index order (auto-created)
- `cache/manifest.json` — cache key manifest (auto-created)

## What was built
Embeds all text chunks from Stage 1 into 384-dim vectors and builds a FAISS IndexFlatIP
for fast cosine similarity search. Includes disk caching so re-runs skip re-embedding.

## Key design decisions

### IndexFlatIP (not IndexFlatL2)
- Vectors are L2-normalised → inner product == cosine similarity
- Scores returned are in [0, 1], higher = more similar
- IndexFlatL2 returns distances (lower = better) and would break Stage 3 confidence thresholds
- Test verifies norms ≈ 1.0 to catch any regression

### Sequential embedding (no ThreadPoolExecutor)
- `model.encode()` is called once with all texts; sentence-transformers handles batching internally
- DO NOT wrap in ThreadPoolExecutor — causes segfault on macOS arm64 due to conflict with
  loky/joblib parallelism used internally by sentence-transformers
- Progress shown via sentence-transformers' built-in tqdm bar (`show_progress_bar=True`)
- MPS backend is used automatically on Apple Silicon

### Disk cache
- FAISS index saved to `cache/index.faiss`, metadata to `cache/chunks_metadata.json`
- Cache keyed on source file fingerprints (path + mtime + size) — different DRHP → fresh index
- On second run, cache is loaded in ~1 second (skips re-embedding)
- `force_rebuild=True` to bypass cache
- Metadata strips DataFrame objects (tables) before JSON serialisation

### search() utility
- Embeds a query string, runs FAISS search, returns top-k results with `score` field added
- Optional `source_filter` to restrict results to a specific file (used in Stage 3 for style-only chunks from the reference DRHP)
- Fetches `top_k * 5` candidates when filtering, then trims to top_k after filter

## Test results (real DRHP, 1721 chunks)
- All 1721 chunks embedded successfully
- Vector norms: mean=1.0000 ✓
- Cache save/reload working ✓
- Search scores in [0, 1]: 0.515 (incorporation), 0.659 (financials), 0.464 (promoters)
- Source-filtered search working ✓
- Embedding time: ~2 minutes for 1721 chunks on Apple Silicon (MPS)

## Package versions
- `sentence-transformers` (latest)
- `faiss-cpu` (latest)
- `numpy>=1.26`
