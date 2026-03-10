# System Boundaries — Input File Limits

Observed from running the pipeline on real data (BillionBrains DRHP, Apple Silicon MPS).
All figures are practical estimates, not hard limits enforced by code.

---

## Baseline (what we tested)

| File                        | Size  | Pages | Chunks |
|-----------------------------|-------|-------|--------|
| `inputs/sample_drhp.pdf`    | 12 MB | 568   | 1,721  |
| `inputs/company_description.txt` | ~1 KB | —  | ~2     |
| **Total**                   | ~12 MB | 568  | ~1,723 |

Embedding time: ~2 min on Apple Silicon MPS
Peak memory: ~200–300 MB
FAISS index size on disk: ~2.6 MB (`1723 × 384 × 4 bytes`)

---

## Recommended Limits (comfortable operating range)

| Input                        | Recommended Max      | Why                                   |
|------------------------------|----------------------|---------------------------------------|
| `sample_drhp.pdf` (reference)| 600 pages / 25 MB    | Style-only; excess pages add noise    |
| Any single financial PDF     | 150 pages / 10 MB    | Financials are dense; fewer chunks needed |
| Any single supporting doc    | 100 pages / 8 MB     | ROC filings, company descriptions etc |
| **Total across all files**   | **1,500 pages / 60 MB** | Keeps embedding < 4 min, RAM < 500 MB |

---

## What Happens Beyond These Limits

### 1,500 – 3,000 pages (stretched but workable)

| Metric            | Impact                                          |
|-------------------|-------------------------------------------------|
| Chunks            | ~3,000 – 6,000                                  |
| Embedding time    | 4 – 8 minutes (MPS) / 10 – 20 minutes (CPU)    |
| Peak RAM          | 500 MB – 1 GB                                   |
| FAISS index (disk)| 7 – 15 MB                                       |
| Retrieval quality | Slight dilution — more irrelevant chunks compete|
| Cache reload      | Still ~1 s (FAISS load is fast)                 |

### 3,000+ pages (not recommended without changes)

| Metric            | Impact                                              |
|-------------------|-----------------------------------------------------|
| Chunks            | 6,000+                                              |
| Embedding time    | 15 – 30+ minutes                                    |
| Peak RAM          | 1.5 GB+ (two copies of chunks during `build_index`) |
| Retrieval quality | Degrades unless `top_k` candidates increased        |
| Risk              | OOM on machines with < 8 GB RAM                     |

---

## Memory Breakdown (per 1,000 chunks)

| Component                        | RAM usage        |
|----------------------------------|------------------|
| `chunks` list (Stage 1 output)   | ~30 MB           |
| `metadata` list (Stage 2 copy)   | ~30 MB           |
| FAISS IndexFlatIP vectors        | ~1.5 MB          |
| Embedding model (`all-MiniLM-L6-v2`) | ~90 MB (one-time, shared) |
| **Per-1000-chunk overhead**      | **~60 MB** (excl. model) |

Both `chunks` and `metadata` live in memory simultaneously during `build_index()` — the peak is roughly **2× the chunk list size** at that moment.

---

## Multiple Supporting Documents — Practical Guidance

Adding several financial PDFs is fine within these bounds:

```
inputs/
├── sample_drhp.pdf          ← reference only  (≤ 600 pages)
├── financials_fy25.pdf      ← data source      (≤ 150 pages)
├── financials_fy24.pdf      ← data source      (≤ 150 pages)
├── roc_filing.pdf           ← data source      (≤ 100 pages)
└── company_description.txt  ← data source      (any size)
```

**Total ≤ 1,000 pages / ≤ 50 MB** → embedding ~3 min, RAM ~400 MB — comfortable.

If you add more files, watch the chunk count printed by Stage 1:
- < 3,000 chunks → proceed normally
- 3,000 – 6,000 chunks → expect longer embedding; RAM usage up
- > 6,000 chunks → consider splitting into separate runs or upgrading to streaming

---

## What Would Need to Change for Larger Scale

| Requirement              | Change needed                                         |
|--------------------------|-------------------------------------------------------|
| > 6,000 chunks           | Stream chunks in batches; don't hold all in memory    |
| > 10,000 chunks          | Replace `IndexFlatIP` with `IndexIVFFlat` (approximate) |
| Multi-DRHP batch runs    | Persist chunks to SQLite instead of in-memory list    |
| < 4 GB RAM machine       | Lower `BATCH_SIZE` in embed.py (currently 64)         |
| Very large scanned PDFs  | OCR pre-processing outside this pipeline (not supported) |

---

## Quick Check Before Adding Files

Run Stage 1 and look at the printed chunk count:

```bash
python -c "
from src.dev.ingest import ingest_documents, print_chunk_stats
chunks, tables = ingest_documents(['inputs/sample_drhp.pdf', 'inputs/financials.pdf'])
print_chunk_stats(chunks, tables)
"
```

If `Total chunks` is under 3,000 — proceed. If over, expect longer embedding times.
