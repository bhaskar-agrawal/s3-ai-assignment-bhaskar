"""
Stage 1 test script.

Run:
    python test_stage1.py

Expected output:
    - Total chunks: 10-40 (3-page synthetic PDF)
    - Total tables: 1 (the financial highlights table)
    - Avg chars/chunk: ~1500-2000
    - A few sample chunks printed to screen
"""

import sys
import json
import random
from pathlib import Path

# Make sure we can import from project root (two levels up from src/test/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ingest import ingest_documents, print_chunk_stats

INPUT_FILES = []

# Prefer the PDF if it exists, fall back to the txt version
pdf_path = Path("inputs/sample_drhp.pdf")
txt_path = Path("inputs/sample_drhp.txt")
desc_path = Path("inputs/company_description.txt")

if pdf_path.exists():
    INPUT_FILES.append(str(pdf_path))
elif txt_path.exists():
    INPUT_FILES.append(str(txt_path))
else:
    print("ERROR: No sample input found. Run first:")
    print("    python create_sample_input.py")
    sys.exit(1)

if desc_path.exists():
    INPUT_FILES.append(str(desc_path))

print(f"Ingesting: {INPUT_FILES}\n")
chunks, tables = ingest_documents(INPUT_FILES)

print("=" * 60)
print("SUMMARY")
print("=" * 60)
print_chunk_stats(chunks, tables)

print()
print("=" * 60)
print("CHUNK SCHEMA (first chunk)")
print("=" * 60)
if chunks:
    c = chunks[0]
    print(json.dumps({k: v for k, v in c.items() if k != "text"}, indent=2))
    print(f"text (first 300 chars):\n{c['text'][:300]}")

print()
print("=" * 60)
print("3 RANDOM CHUNKS")
print("=" * 60)
for c in random.sample(chunks, min(3, len(chunks))):
    print(f"--- chunk_id={c['chunk_id']}  page={c['page']}  source={c['source']}  tokens={c['token_count']} ---")
    if c["section_header"]:
        print(f"    section_header: {c['section_header']}")
    print(c["text"][:400])
    print()

if tables:
    print("=" * 60)
    print("FIRST TABLE (head)")
    print("=" * 60)
    print(f"Source: {tables[0]['source']}, Page: {tables[0]['page']}")
    print(tables[0]["table"].head())

print()
print("Stage 1 PASSED" if chunks else "Stage 1 FAILED — no chunks produced")
