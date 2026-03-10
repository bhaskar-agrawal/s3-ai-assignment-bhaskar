"""
Stage 1: Ingest & Parse

Converts raw input files (PDFs, text files) into structured text chunks with metadata.
Extracts tables separately. Produces chunks ready for embedding in Stage 2.

Parallelism strategy:
- Text extraction is independent per page → extracted in parallel batches using ThreadPoolExecutor
- Chunking with cross-page overlap must be sequential → done after sorting each batch by page number
- Memory is bounded to one batch of pages at a time (BATCH_SIZE pages)
"""

import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Tuple, Generator, Optional

import tiktoken
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50
MIN_CHARS_PER_PAGE = 100          # pages below this are skipped
BATCH_SIZE = 20                   # pages extracted in parallel per batch
MAX_WORKERS = min(8, os.cpu_count() or 4)  # parallel extraction threads

_tokenizer = tiktoken.get_encoding("cl100k_base")

# ---------------------------------------------------------------------------
# DRHP section header patterns (soft tagging only)
# ---------------------------------------------------------------------------
_SECTION_HEADER_PATTERNS = [
    r"^BUSINESS OVERVIEW",
    r"^RISK FACTORS",
    r"^CAPITAL STRUCTURE",
    r"^OBJECTS OF THE ISSUE",
    r"^GROUP COMPANIES",
    r"^FINANCIAL STATEMENTS",
    r"^MANAGEMENT.S DISCUSSION",
    r"^PROMOTERS AND PROMOTER GROUP",
    r"^LEGAL AND OTHER INFORMATION",
    r"^SUMMARY OF THE OFFER",
    r"^OUR HISTORY",
    r"^OUR BUSINESS",
    r"^OUR MANAGEMENT",
    r"^OUR SUBSIDIARIES",
    r"^INDUSTRY OVERVIEW",
    r"^TERMS OF THE ISSUE",
    r"^DECLARATIONS",
]
_SECTION_RE = re.compile(
    "|".join(_SECTION_HEADER_PATTERNS), re.IGNORECASE | re.MULTILINE
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_documents(file_paths: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """
    Ingest a list of input files and return (chunks, tables).

    PDFs are parsed with parallel page extraction (BATCH_SIZE pages at a time)
    then sequential chunking to preserve cross-page overlap.

    Returns:
        chunks : List[Dict] — chunk_id, text, page, source, token_count, section_header
        tables : List[Dict] — table (DataFrame), page, source
    """
    all_chunks: List[Dict] = []
    all_tables: List[Dict] = []
    chunk_counter = 0

    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            print(f"[ingest] WARNING: file not found, skipping: {file_path}", flush=True)
            continue

        ext = path.suffix.lower()
        if ext == ".pdf":
            for item in _stream_pdf(str(path), chunk_counter):
                if item["_type"] == "chunk":
                    del item["_type"]
                    all_chunks.append(item)
                    chunk_counter += 1
                else:
                    del item["_type"]
                    all_tables.append(item)
        elif ext in (".txt", ".md"):
            for item in _stream_text_file(str(path), chunk_counter):
                del item["_type"]
                all_chunks.append(item)
                chunk_counter += 1
        else:
            print(f"[ingest] WARNING: unsupported file type, skipping: {file_path}", flush=True)

    print(
        f"[ingest] ✓ complete: {len(all_chunks)} chunks, {len(all_tables)} tables "
        f"from {len(file_paths)} file(s)",
        flush=True,
    )
    return all_chunks, all_tables


# ---------------------------------------------------------------------------
# PDF: parallel extraction + sequential chunking
# ---------------------------------------------------------------------------

def _stream_pdf(file_path: str, start_chunk_id: int = 0) -> Generator[Dict, None, None]:
    """
    Yield chunks and tables from a PDF.

    Extraction is parallelised: BATCH_SIZE pages are extracted concurrently
    using ThreadPoolExecutor (each thread opens its own file handle — thread-safe).
    Chunking is sequential within each batch to maintain cross-page token overlap.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Install pdfplumber: pip install pdfplumber")

    source = Path(file_path).name
    chunk_counter = start_chunk_id
    total_chars = 0
    skipped_pages = 0
    overlap_tokens: List[int] = []

    # Get total page count without loading content
    with pdfplumber.open(file_path) as pdf:
        num_pages = len(pdf.pages)

    print(
        f"[ingest] {source}: {num_pages} pages — extracting in parallel "
        f"(batch={BATCH_SIZE}, workers={MAX_WORKERS}) ...",
        flush=True,
    )

    # Process in batches
    for batch_start in range(0, num_pages, BATCH_SIZE):
        batch_indices = range(batch_start, min(batch_start + BATCH_SIZE, num_pages))

        # --- Parallel extraction for this batch ---
        batch_results: Dict[int, Tuple[str, List[Dict]]] = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_page = {
                executor.submit(_extract_page_worker, file_path, i, source): i
                for i in batch_indices
            }
            for future in as_completed(future_to_page):
                page_index = future_to_page[future]
                page_num = page_index + 1  # 1-indexed
                try:
                    text, tables = future.result()
                    batch_results[page_num] = (text, tables)
                except Exception as e:
                    print(f"[ingest]   page {page_num} extraction error: {e}", flush=True)
                    batch_results[page_num] = ("", [])

        # --- Sequential chunking over sorted batch ---
        for page_num in sorted(batch_results.keys()):
            text, tables = batch_results[page_num]
            total_chars += len(text)

            if len(text.strip()) < MIN_CHARS_PER_PAGE:
                skipped_pages += 1
                print(
                    f"[ingest]   page {page_num}/{num_pages} — skipped "
                    f"(low text: {len(text)} chars)",
                    flush=True,
                )
                overlap_tokens = []
                continue

            # Yield tables first
            for table_record in tables:
                yield {"_type": "table", **table_record}

            # Chunk with cross-page overlap
            tokens = _tokenizer.encode(text)
            if overlap_tokens:
                tokens = overlap_tokens + tokens

            start = 0
            last_chunk_tokens: List[int] = []

            while start < len(tokens):
                end = min(start + CHUNK_SIZE_TOKENS, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = _tokenizer.decode(chunk_tokens)

                yield {
                    "_type": "chunk",
                    "chunk_id": f"chunk_{chunk_counter:05d}",
                    "text": chunk_text,
                    "page": page_num,
                    "source": source,
                    "token_count": len(chunk_tokens),
                    "section_header": _detect_section_header(chunk_text),
                }
                chunk_counter += 1
                last_chunk_tokens = chunk_tokens

                step = CHUNK_SIZE_TOKENS - CHUNK_OVERLAP_TOKENS
                start += step
                if end == len(tokens):
                    break

            overlap_tokens = last_chunk_tokens[-CHUNK_OVERLAP_TOKENS:] if last_chunk_tokens else []

        # Progress after each batch
        last_page_in_batch = min(batch_start + BATCH_SIZE, num_pages)
        pct = last_page_in_batch / num_pages * 100
        chunks_so_far = chunk_counter - start_chunk_id
        print(
            f"[ingest]   pages {batch_start + 1}-{last_page_in_batch}/{num_pages} "
            f"({pct:.0f}%) — {chunks_so_far} chunks",
            flush=True,
        )

    # Scanned PDF warning
    avg_chars = total_chars / max(num_pages, 1)
    if avg_chars < MIN_CHARS_PER_PAGE:
        print(
            f"[ingest] WARNING: {source} yields only {avg_chars:.0f} chars/page on average. "
            "This PDF may be scanned — provide a text-based PDF.",
            flush=True,
        )

    new_chunks = chunk_counter - start_chunk_id
    print(
        f"[ingest] {source}: done — {new_chunks} chunks, "
        f"{num_pages - skipped_pages} pages used, {skipped_pages} skipped",
        flush=True,
    )


def _extract_page_worker(file_path: str, page_index: int, source: str) -> Tuple[str, List[Dict]]:
    """
    Extract text and tables from a single page.
    Opens its own pdfplumber handle — safe to call from multiple threads.
    """
    import pdfplumber
    page_num = page_index + 1
    try:
        with pdfplumber.open(file_path) as pdf:
            page_obj = pdf.pages[page_index]
            text = _extract_page_text(page_obj, file_path, page_num)
            tables = _extract_tables_from_page(page_obj, page_num, source)
        return text, tables
    except Exception as e:
        logger.debug(f"Worker failed page {page_num}: {e}")
        return "", []


def _extract_page_text(page_obj, file_path: str, page_num: int) -> str:
    """Extract text from a pdfplumber page, with multi-column and pymupdf fallback."""
    text = page_obj.extract_text(layout=True) or ""

    if len(text.strip()) < 50:
        text = _pymupdf_page(file_path, page_num - 1)

    if len(text.strip()) < 50:
        return ""

    # Multi-column detection
    try:
        words = page_obj.extract_words()
        if words and len(words) > 20:
            col_text = _handle_columns(page_obj, words)
            if col_text:
                text = col_text
    except Exception:
        pass

    return text


def _handle_columns(page_obj, words: List[Dict]) -> str:
    """Split two-column pages into left-then-right text flow."""
    page_width = page_obj.width
    midpoint = page_width / 2

    left_words = [w for w in words if w["x1"] < midpoint - 20]
    right_words = [w for w in words if w["x0"] > midpoint + 20]

    if not left_words or not right_words:
        return ""
    if len(left_words) < len(words) * 0.2 or len(right_words) < len(words) * 0.2:
        return ""

    try:
        left_text = page_obj.within_bbox((0, 0, midpoint, page_obj.height)).extract_text() or ""
        right_text = page_obj.within_bbox((midpoint, 0, page_width, page_obj.height)).extract_text() or ""
        combined = (left_text.strip() + "\n\n" + right_text.strip()).strip()
        return combined if combined else ""
    except Exception:
        return ""


def _pymupdf_page(file_path: str, page_index: int) -> str:
    """Fallback: extract text from one page using pymupdf."""
    try:
        import fitz
        doc = fitz.open(file_path)
        text = doc[page_index].get_text()
        doc.close()
        return text or ""
    except Exception as e:
        logger.debug(f"pymupdf fallback failed page {page_index}: {e}")
        return ""


def _extract_tables_from_page(page_obj, page_num: int, source: str) -> List[Dict]:
    """Extract all tables from a single page."""
    results = []
    try:
        raw_tables = page_obj.extract_tables() or []
        for raw_table in raw_tables:
            if not raw_table or len(raw_table) < 2:
                continue
            try:
                header = raw_table[0]
                rows = [r for r in raw_table[1:] if any(c for c in r)]
                if not header or not rows:
                    continue
                df = pd.DataFrame(rows, columns=header)
                results.append({"table": df, "page": page_num, "source": source})
            except Exception as e:
                logger.debug(f"Table parse error page {page_num}: {e}")
    except Exception as e:
        logger.debug(f"Table extraction failed page {page_num}: {e}")
    return results


# ---------------------------------------------------------------------------
# Text file streaming
# ---------------------------------------------------------------------------

def _stream_text_file(file_path: str, start_chunk_id: int = 0) -> Generator[Dict, None, None]:
    """Chunk a plain text file, yielding one chunk at a time."""
    source = Path(file_path).name
    print(f"[ingest] {source}: reading ...", flush=True)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    tokens = _tokenizer.encode(text)
    chunk_counter = start_chunk_id
    start = 0

    while start < len(tokens):
        end = min(start + CHUNK_SIZE_TOKENS, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = _tokenizer.decode(chunk_tokens)

        yield {
            "_type": "chunk",
            "chunk_id": f"chunk_{chunk_counter:05d}",
            "text": chunk_text,
            "page": 1,
            "source": source,
            "token_count": len(chunk_tokens),
            "section_header": _detect_section_header(chunk_text),
        }
        chunk_counter += 1

        step = CHUNK_SIZE_TOKENS - CHUNK_OVERLAP_TOKENS
        start += step
        if end == len(tokens):
            break

    print(f"[ingest] {source}: done — {chunk_counter - start_chunk_id} chunks", flush=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_section_header(text: str) -> Optional[str]:
    """Soft-detect the nearest DRHP section header in a chunk."""
    match = _SECTION_RE.search(text)
    return match.group(0).strip()[:60] if match else None


def print_chunk_stats(chunks: List[Dict], tables: List[Dict]) -> None:
    """Print a summary of ingestion results."""
    print(f"Total chunks : {len(chunks)}")
    print(f"Total tables : {len(tables)}")
    if chunks:
        avg_chars = sum(len(c["text"]) for c in chunks) / len(chunks)
        avg_tokens = sum(c["token_count"] for c in chunks) / len(chunks)
        sources = sorted({c["source"] for c in chunks})
        tagged = sum(1 for c in chunks if c["section_header"])
        print(f"Avg chars/chunk  : {avg_chars:.0f}")
        print(f"Avg tokens/chunk : {avg_tokens:.0f}")
        print(f"Sources          : {sources}")
        print(f"Section-tagged   : {tagged}/{len(chunks)} chunks")
    if tables:
        print(f"Table sources    : {sorted({t['source'] for t in tables})}")
