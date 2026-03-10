# Stage 1: Ingest & Parse — Implementation Notes

## Files
- `src/ingest.py` — main module
- `src/dev/ingest.py` — dev copy (kept in sync manually with src/ingest.py)
- `src/test/test_stage1.py` — test script (run from project root)
- `create_sample_input.py` — generates synthetic 3-page test PDF with real bordered table

## What was built
Streaming PDF and text file parser that produces text chunks + extracted tables for Stage 2.

## Key design decisions

### Streaming (page-by-page)
- PDFs are processed one page at a time — no full-document text held in memory at once
- Each page is chunked immediately and discarded before the next page is read
- Cross-page overlap: last 50 tokens of page N are prepended to page N+1 to avoid splitting facts at boundaries
- Same approach applies to all input files (DRHP, financials, ROC filings) regardless of size

### Chunking
- Target: 400 tokens per chunk, 50-token overlap between consecutive chunks
- Tokenizer: `tiktoken cl100k_base`
- Each chunk carries: `chunk_id`, `text`, `page`, `source`, `token_count`, `section_header`

### Multi-column layout handling
- Cover pages and some body pages in real DRHPs use two-column layouts
- Detection: if >20% of words fall on each side of the page midpoint, split into left/right bboxes
- Known limitation: column bbox boundary sometimes clips mid-word on dense table pages (low impact — those pages score low in retrieval)

### Empty page skipping
- Pages with <100 chars are skipped (images, diagrams, fully scanned pages)
- Overlap buffer is reset across skipped pages

### Table extraction
- `pdfplumber extract_tables()` runs per page during streaming
- Stored as pandas DataFrames with `page` and `source` metadata
- Used later in Stage 4 for structured financial data extraction

### pymupdf fallback
- If pdfplumber yields <50 chars on a page, pymupdf (`fitz`) is tried as fallback

### Progress logging
- `print()` with `flush=True` used (not logging module) so output appears immediately in terminal
- Progress printed every 50 pages for large files, every page for small files
- Format: `[ingest] page X/total (pct%) — N chunks so far`
- Skipped pages explicitly called out: `[ingest] page X/total — skipped (low text: N chars)`
- Summary at end: `[ingest] ✓ complete: N chunks, M tables from K file(s)`

## Package versions (Python 3.13, Apple Silicon / arm64)
- `pdfplumber>=0.10.3` (0.11.x works on Py 3.13)
- `pymupdf>=1.24.0` (1.23.x has no arm64 wheel — fails to compile)
- `tiktoken>=0.5.2`
- `pandas>=2.2` (2.1.x has no Py 3.13 wheel)
- `fpdf2` (for synthetic PDF generation only, not in main pipeline)
- Venv at project root: `.venv/` (`source .venv/bin/activate`)

## Test results (real DRHP — BillionBrains, 568 pages, 12MB)
- 1721 chunks, 703 tables
- 7 low-text pages correctly skipped
- Avg 347 tokens/chunk
- 58 section-tagged chunks
- Runtime: ~30 seconds

## Sample progress output
```
[ingest] sample_drhp.pdf: 568 pages — starting ...
[ingest]   page 50/568 (9%) — 170 chunks so far
[ingest]   page 100/568 (18%) — 330 chunks so far
[ingest]   page 276/568 — skipped (low text: 0 chars)
...
[ingest]   page 568/568 (100%) — 1718 chunks so far
[ingest] sample_drhp.pdf: done — 1720 chunks, 568 pages parsed
[ingest] ✓ complete: 1721 chunks, 703 tables from 2 file(s)
```

## Known issues
- Multi-column word-clip in dense table pages (low impact on retrieval quality)
- Section header detection is noisy (ALL CAPS pervasive in DRHPs) — used only as soft filter, not for data routing
