# DRHP Drafting Agent — Project Memory

## Project
AI agent that drafts the Business Overview section of a DRHP (Indian IPO filing).
5-stage pipeline: Ingest → Embed → Retrieve → Extract → Draft.
Design doc: `plan.md` (1160 lines, fully up to date).

## Stage Status
| Stage | Status | Notes |
|-------|--------|-------|
| 1: Ingest & Parse | ✅ COMPLETE | see `memory/step1.md` |
| 2: Embed & FAISS  | ✅ COMPLETE | see `memory/step2.md` |
| 3: Retrieve       | ✅ COMPLETE | see `memory/step3.md` |
| 4: Extract        | not started | |
| 5: Draft          | not started | |

## Environment
- Python 3.13, Apple Silicon (arm64)
- Venv: `.venv/` at project root — `source .venv/bin/activate`
- Use `pymupdf>=1.24.0` and `pandas>=2.2` — older pinned versions fail on Py 3.13 / arm64

## Key files
```
src/
├── dev/ingest.py        Stage 1 module (canonical — src/ingest.py was removed as duplicate)
├── dev/embed.py         Stage 2 module
├── dev/retrieve.py      Stage 3 module
└── test/
    ├── test_stage1.py   Stage 1 test
    ├── test_stage2.py   Stage 2 test
    └── test_stage3.py   Stage 3 test
inputs/
├── sample_drhp.pdf      real 568-page DRHP (BillionBrains, 12MB)
└── company_description.txt
cache/
├── index.faiss          FAISS index (auto-created by Stage 2)
├── chunks_metadata.json chunk metadata (auto-created by Stage 2)
└── manifest.json        cache key manifest (auto-created by Stage 2)
create_sample_input.py   generates synthetic 3-page test PDF
memory/
├── MEMORY.md            this file
├── step1.md             Stage 1 detailed notes
└── step2.md             Stage 2 detailed notes
```

## User preferences
- All packages in `.venv/` only — never install globally
- Keep `src/dev/` and `src/test/` structure (pre-existing convention)
- Progress output: use `print(..., flush=True)` not logging module
- Memory files go inside repo at `memory/` so they are visible in the editor
