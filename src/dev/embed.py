"""
Stage 2: Embed & Index

Converts text chunks into vector embeddings and builds a FAISS index for semantic retrieval.

Parallelism: batches of chunks are embedded concurrently via ThreadPoolExecutor.
Progress is tracked with a thread-safe counter so lines print in order.

Cache: keyed on the source files actually passed in (path + mtime + size).
Different DRHPs → different cache key → fresh index automatically.

Index type: IndexFlatIP (inner product) with L2-normalised vectors = cosine similarity.
DO NOT use IndexFlatL2 — breaks Stage 3 confidence thresholds (which expect [0,1], higher=better).
"""

import os
import sys
import json
import time
import hashlib
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Suppress sentence-transformers / transformers verbose INFO logs
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # 22M params, 384-dim, runs on CPU/MPS
EMBEDDING_DIM   = 384
BATCH_SIZE      = 64

CACHE_DIR      = Path("cache")
INDEX_PATH     = CACHE_DIR / "index.faiss"
METADATA_PATH  = CACHE_DIR / "chunks_metadata.json"
MANIFEST_PATH  = CACHE_DIR / "manifest.json"   # tracks which files built this cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_index(
    chunks: List[Dict],
    source_files: Optional[List[str]] = None,
    force_rebuild: bool = False,
) -> Tuple[object, List[Dict]]:
    """
    Build (or load from cache) a FAISS IndexFlatIP over all chunk embeddings.

    Cache is keyed on source_files (path + mtime + size). If you pass a different
    DRHP the cache key won't match and a fresh index is built automatically.

    Args:
        chunks:        Chunk dicts from Stage 1 (must have 'text' key).
        source_files:  Paths of the original input files used to produce chunks.
                       Used to compute the cache key. If None, cache is skipped.
        force_rebuild: Always rebuild, ignoring cache.

    Returns:
        index    : faiss.IndexFlatIP
        metadata : List[Dict] in same order as index vectors
    """
    CACHE_DIR.mkdir(exist_ok=True)

    if not force_rebuild and source_files:
        cache_key = _compute_cache_key(source_files)
        if _cache_is_valid(cache_key):
            print("[embed] Cache hit — same input files, loading index from disk ...", flush=True)
            index, metadata = _load_from_cache()
            print(f"[embed] ✓ loaded {index.ntotal} vectors from cache", flush=True)
            return index, metadata
        else:
            print("[embed] Cache miss — input files changed, rebuilding index ...", flush=True)
    elif not source_files:
        print("[embed] No source_files provided — skipping cache lookup, building fresh ...", flush=True)

    model = _load_model()
    embeddings, metadata = _embed_all(chunks, model)
    index = _build_faiss_index(embeddings)
    _save_to_cache(index, metadata, source_files)

    print(f"[embed] ✓ index built: {index.ntotal} vectors, dim={index.d}", flush=True)
    return index, metadata


def search(
    query: str,
    index,
    metadata: List[Dict],
    top_k: int = 10,
    source_filter: Optional[str] = None,
    model=None,
) -> List[Dict]:
    """
    Embed a query and return top-k most similar chunks (cosine similarity).

    Args:
        source_filter: If set, only return chunks from this source filename.
                       Used in Stage 3 to retrieve style-only chunks from the reference DRHP.
    """
    if model is None:
        model = _load_model()

    vec = model.encode([query], normalize_embeddings=True, show_progress_bar=False).astype("float32")

    fetch_k = min(top_k * 5 if source_filter else top_k, index.ntotal)
    scores, indices = index.search(vec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        chunk = dict(metadata[idx])
        chunk["score"] = float(score)
        if source_filter and chunk.get("source") != source_filter:
            continue
        results.append(chunk)
        if len(results) >= top_k:
            break

    return results


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model():
    """Load sentence-transformers model. Downloads once, cached in ~/.cache after."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError("pip install sentence-transformers")

    print(f"[embed] Loading model '{EMBEDDING_MODEL}' ...", flush=True)
    t0 = time.time()
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"[embed] Model ready ({time.time() - t0:.1f}s)", flush=True)
    return model


# ---------------------------------------------------------------------------
# Parallel embedding with clean progress output
# ---------------------------------------------------------------------------

def _embed_all(chunks: List[Dict], model) -> Tuple[np.ndarray, List[Dict]]:
    """
    Embed all chunks sequentially using model.encode() with internal batching.

    sentence-transformers handles batching internally and uses MPS/CUDA when available.
    A custom ThreadPoolExecutor causes segfaults on macOS arm64 due to conflicts with
    the loky/joblib parallelism used internally by sentence-transformers.
    """
    texts = [c["text"] for c in chunks]
    n = len(texts)
    total_batches = (n + BATCH_SIZE - 1) // BATCH_SIZE

    print(
        f"[embed] Embedding {n} chunks → {total_batches} batches (batch_size={BATCH_SIZE})",
        flush=True,
    )

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=BATCH_SIZE,
    ).astype("float32")

    # Verify normalisation
    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        print("[embed] WARNING: re-normalising embeddings ...", flush=True)
        embeddings /= norms[:, np.newaxis]

    print(f"[embed]   {n}/{n} chunks embedded ✓", flush=True)
    return embeddings, chunks


# ---------------------------------------------------------------------------
# FAISS index
# ---------------------------------------------------------------------------

def _build_faiss_index(embeddings: np.ndarray):
    """IndexFlatIP: inner product search = cosine similarity for unit-norm vectors."""
    try:
        import faiss
    except ImportError:
        raise ImportError("pip install faiss-cpu")

    _, d = embeddings.shape
    assert d == EMBEDDING_DIM, f"Expected dim {EMBEDDING_DIM}, got {d}"
    index = faiss.IndexFlatIP(d)
    index.add(embeddings)
    print(f"[embed] FAISS index ready: {index.ntotal} vectors, dim={index.d}", flush=True)
    return index


# ---------------------------------------------------------------------------
# Cache — keyed on input file fingerprints
# ---------------------------------------------------------------------------

def _compute_cache_key(source_files: List[str]) -> str:
    """
    Compute a cache key from the sorted list of source files.
    Key = MD5 of (path + mtime + size) for each file, sorted by path.
    This means any file change (new DRHP, updated financials) invalidates the cache.
    """
    parts = []
    for fp in sorted(source_files):
        p = Path(fp)
        if p.exists():
            stat = p.stat()
            parts.append(f"{p.resolve()}:{stat.st_mtime}:{stat.st_size}")
        else:
            parts.append(f"{fp}:missing")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _cache_is_valid(cache_key: str) -> bool:
    """Return True only if cache files exist AND were built from the same input files."""
    if not (INDEX_PATH.exists() and METADATA_PATH.exists() and MANIFEST_PATH.exists()):
        return False
    try:
        manifest = json.loads(MANIFEST_PATH.read_text())
        return manifest.get("cache_key") == cache_key
    except Exception:
        return False


def _save_to_cache(index, metadata: List[Dict], source_files: Optional[List[str]]) -> None:
    """Persist FAISS index, metadata, and manifest to disk."""
    try:
        import faiss
        faiss.write_index(index, str(INDEX_PATH))
    except Exception as e:
        print(f"[embed] WARNING: could not save FAISS index: {e}", flush=True)
        return

    serialisable = [{k: v for k, v in c.items() if k != "table"} for c in metadata]
    METADATA_PATH.write_text(json.dumps(serialisable, ensure_ascii=False), encoding="utf-8")

    # Write manifest
    manifest = {
        "cache_key": _compute_cache_key(source_files) if source_files else None,
        "source_files": source_files or [],
        "num_vectors": index.ntotal,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[embed] Cache saved → {CACHE_DIR}/  (key={manifest['cache_key'][:8]}...)", flush=True)


def _load_from_cache() -> Tuple[object, List[Dict]]:
    """Load FAISS index and metadata from disk."""
    try:
        import faiss
        index = faiss.read_index(str(INDEX_PATH))
    except Exception as e:
        raise RuntimeError(f"Failed to load FAISS index: {e}")
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return index, metadata
