"""
DRHP Drafting Agent — Main entry point.

Usage:
    python main.py [--input-dir DIR] [--output-dir DIR] [--force-rebuild]

Arguments:
    --input-dir   DIR   Directory containing input files (default: inputs/)
                        Rules:
                          sample_drhp.pdf / sample_drhp.txt  → reference DRHP (optional)
                          all other .pdf / .txt / .md files  → company context documents
    --output-dir  DIR   Where to write output files (default: outputs/)
    --force-rebuild     Force FAISS index rebuild even if cache exists

Outputs:
    <output-dir>/business_overview_draft.txt
    <output-dir>/review_notes.txt
    <output-dir>/extraction_log.json
"""

import sys
import os
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split("#")[0].strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)

sys.path.insert(0, str(Path(__file__).parent))

from src.dev.ingest import ingest_documents, tables_to_chunks
from src.dev.embed import build_index, _load_model
from src.dev.retrieve import retrieve_all
from src.dev.extract import extract_all
from src.dev.draft import draft_all, OUTPUT_DIR as DEFAULT_OUTPUT_DIR
from src.dev.llm_client import LLMClient

SUPPORTED_EXTS = {".pdf", ".txt", ".md"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Draft the Business Overview section of a DRHP."
    )
    parser.add_argument(
        "--input-dir",
        default="inputs",
        metavar="DIR",
        help="Directory containing input files (default: inputs/)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        metavar="DIR",
        help="Directory to write outputs to (default: outputs/)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force FAISS index rebuild even if cache exists",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files(input_dir: Path):
    """
    Returns (drhp_source, input_files) from the input directory.

    drhp_source  — basename of the reference DRHP, or None if not found
    input_files  — list of all file paths to ingest (reference DRHP first)
    """
    if not input_dir.is_dir():
        print(f"ERROR: input directory not found: {input_dir}")
        sys.exit(1)

    # Reference DRHP
    drhp_file: Path | None = None
    for candidate in ["sample_drhp.pdf", "sample_drhp.txt"]:
        p = input_dir / candidate
        if p.exists():
            drhp_file = p
            break

    all_files = sorted(
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
    )

    if drhp_file is None:
        print(f"[main] No sample_drhp.pdf found in {input_dir}/")
        print("[main] Proceeding without style reference — standard DRHP language will be used.")
        context_files = all_files
        input_files   = [str(f) for f in context_files]
        drhp_source   = None
    else:
        context_files = [f for f in all_files if f.name != drhp_file.name]
        input_files   = [str(drhp_file)] + [str(f) for f in context_files]
        drhp_source   = drhp_file.name

    if not input_files:
        print(f"ERROR: No input files found in {input_dir}/")
        print(f"  Add .pdf / .txt / .md files and re-run.")
        sys.exit(1)

    if not context_files and drhp_file:
        print("[main] WARNING: No context documents found — draft will be based on the reference DRHP only.")

    print(f"[main] Input directory : {input_dir.resolve()}")
    print(f"[main] Reference DRHP  : {drhp_source or '(none)'}")
    print(f"[main] Context files   : {[f.name for f in context_files] or '(none)'}")
    print()

    return drhp_source, input_files


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(input_dir: Path, output_dir: Path, force_rebuild: bool):
    # Override default output directory in draft module
    import src.dev.draft as draft_module
    draft_module.OUTPUT_DIR = output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Discover files
    drhp_source, input_files = discover_files(input_dir)

    # Stage 1: Ingest
    print("[main] Stage 1: Ingesting documents ...")
    chunks, tables = ingest_documents(input_files)
    table_chunks = tables_to_chunks(tables, start_chunk_id=len(chunks))
    chunks = chunks + table_chunks
    print(f"[main]   {len(chunks)} chunks ({len(table_chunks)} from tables), {len(tables)} raw tables\n")

    # Load embedding model once — reused for both build_index and retrieve_all
    print("[main] Loading embedding model ...")
    model = _load_model()
    print()

    # Stage 2: Embed
    print("[main] Stage 2: Building FAISS index ...")
    index, metadata = build_index(chunks, source_files=input_files, force_rebuild=force_rebuild, model=model)
    print()

    # Stage 3: Retrieve
    print("[main] Stage 3: Retrieving subsections ...")
    retrieve_results = retrieve_all(index, metadata, drhp_source=drhp_source, model=model)
    print()

    # Stage 4: Extract
    print("[main] Stage 4: Extracting facts ...")
    client = LLMClient()
    extraction_log = extract_all(retrieve_results, client, input_documents=input_files)
    print()

    # Stage 5: Draft
    print("[main] Stage 5: Drafting Business Overview ...")
    full_draft = draft_all(extraction_log, retrieve_results, client, input_documents=input_files)
    print()

    print("[main] Done.")
    print(f"[main]   {output_dir}/business_overview_draft.txt")
    print(f"[main]   {output_dir}/review_notes.txt")
    print(f"[main]   {output_dir}/extraction_log.json")

    return full_draft


if __name__ == "__main__":
    args = parse_args()
    run(
        input_dir     = Path(args.input_dir),
        output_dir    = Path(args.output_dir),
        force_rebuild = args.force_rebuild,
    )
