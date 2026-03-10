"""
Stage 3: Retrieve

For each Business Overview subsection, retrieves the most relevant chunks
from the FAISS index using dual-query semantic search.

Each subsection result contains:
  - data_chunks:         top-8 chunks from supporting docs ONLY — reference DRHP excluded
                         so facts from another company never leak into the new draft
  - style_chunks:        top-3 chunks from the reference DRHP only (style cloning)
  - confidence:          "high" / "medium" / "low" based on top chunk score
  - low_confidence_flag: True if confidence is "low"

Confidence thresholds (IndexFlatIP cosine similarity, normalized vectors):
  HIGH   > 0.65
  MEDIUM 0.45 – 0.65
  LOW    < 0.45
"""

from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONF_HIGH   = 0.65
CONF_MEDIUM = 0.45
TOP_K_DATA  = 8   # data chunks per subsection (after dedup)
TOP_K_STYLE = 3   # style reference chunks per subsection

# 10 Business Overview subsections with primary + secondary retrieval queries
# (from plan.md Stage 3 spec)
SUBSECTIONS = [
    {
        "name": "Corporate History & Background",
        "primary_query": "incorporation date founders company history establishment",
        "secondary_query": "registered office CIN company formation",
    },
    {
        "name": "Nature of Business & Products",
        "primary_query": "products services offerings business segments portfolio",
        "secondary_query": "revenue segments product categories",
    },
    {
        "name": "Manufacturing & Operations",
        "primary_query": "manufacturing plant facility location capacity production",
        "secondary_query": "installed capacity utilization operations",
    },
    {
        "name": "Key Business Strengths",
        "primary_query": "competitive strengths key differentiators advantages",
        "secondary_query": "market position leadership strengths",
    },
    {
        "name": "Promoters & Management",
        "primary_query": "promoter background experience qualification management team",
        "secondary_query": "key managerial personnel directors",
    },
    {
        "name": "Subsidiaries & Associates",
        "primary_query": "subsidiaries group companies associates joint venture",
        "secondary_query": "subsidiary details incorporation ownership",
    },
    {
        "name": "Financial Highlights",
        "primary_query": "revenue profit EBITDA net worth financial performance",
        "secondary_query": "total income PAT financial summary",
    },
    {
        "name": "Geographic Presence",
        "primary_query": "geographic presence states regions offices branches",
        "secondary_query": "distribution network pan India presence",
    },
    {
        "name": "Awards & Certifications",
        "primary_query": "awards certifications ISO accreditation recognition",
        "secondary_query": "quality certification achievements",
    },
    {
        "name": "Future Strategy",
        "primary_query": "growth strategy expansion plans future outlook",
        "secondary_query": "strategic initiatives business plan",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_for_subsection(
    subsection_name: str,
    index,
    metadata: List[Dict],
    drhp_source: Optional[str] = None,
    model=None,
) -> Dict:
    """
    Retrieve data chunks and style chunks for a single subsection.

    Args:
        subsection_name: Must match a name in SUBSECTIONS.
        index:           FAISS IndexFlatIP built in Stage 2.
        metadata:        Chunk metadata list in the same order as the index.
        drhp_source:     Filename (basename, not full path) of the reference DRHP,
                         e.g. "sample_drhp.pdf". Used to filter style chunks.
                         If None, style_chunks will be empty.
        model:           Pre-loaded SentenceTransformer. If None, loaded on demand.

    Returns:
        {
            "subsection":        str,
            "data_chunks":       List[Dict],  # top-8, supporting docs only (never drhp_source)
            "style_chunks":      List[Dict],  # top-3, drhp_source only
            "confidence":        "high" | "medium" | "low",
            "low_confidence_flag": bool,
        }
    """
    from src.dev.embed import search

    sub = next((s for s in SUBSECTIONS if s["name"] == subsection_name), None)
    if sub is None:
        valid = [s["name"] for s in SUBSECTIONS]
        raise ValueError(f"Unknown subsection: '{subsection_name}'. Valid: {valid}")

    # --- Step 3.1 / 3.2: Dual query search ---
    # Fetch more candidates so we still get TOP_K_DATA after excluding drhp_source.
    fetch_k = TOP_K_DATA * 3 if drhp_source else TOP_K_DATA * 2
    primary_hits   = search(sub["primary_query"],   index, metadata, top_k=fetch_k, model=model)
    secondary_hits = search(sub["secondary_query"], index, metadata, top_k=fetch_k, model=model)

    # Deduplicate by chunk_id — keep the higher score if a chunk appears in both,
    # and exclude the reference DRHP so its facts never contaminate the new draft.
    seen: Dict[str, Dict] = {}
    for chunk in primary_hits + secondary_hits:
        if drhp_source and chunk.get("source") == drhp_source:
            continue  # reference DRHP → style only, never used as data
        cid = chunk["chunk_id"]
        if cid not in seen or chunk["score"] > seen[cid]["score"]:
            seen[cid] = chunk

    # Sort descending by score, trim to TOP_K_DATA
    data_chunks = sorted(seen.values(), key=lambda c: c["score"], reverse=True)[:TOP_K_DATA]

    # --- Step 3.3: Style reference (DRHP source only) ---
    style_chunks: List[Dict] = []
    if drhp_source:
        style_chunks = search(
            sub["primary_query"],
            index, metadata,
            top_k=TOP_K_STYLE,
            source_filter=drhp_source,
            model=model,
        )

    # --- Step 3.4: Confidence scoring ---
    top_score = data_chunks[0]["score"] if data_chunks else 0.0
    if top_score >= CONF_HIGH:
        confidence = "high"
    elif top_score >= CONF_MEDIUM:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "subsection":          subsection_name,
        "data_chunks":         data_chunks,
        "style_chunks":        style_chunks,
        "confidence":          confidence,
        "low_confidence_flag": confidence == "low",
    }


def retrieve_all(
    index,
    metadata: List[Dict],
    drhp_source: Optional[str] = None,
    model=None,
) -> List[Dict]:
    """
    Run retrieve_for_subsection for all 10 subsections.

    Loads the embedding model once and reuses it for all queries.

    Returns:
        List of result dicts (one per subsection, in SUBSECTIONS order).
    """
    from src.dev.embed import _load_model

    if model is None:
        model = _load_model()

    results = []
    for sub in SUBSECTIONS:
        print(f"[retrieve] {sub['name']} ...", end=" ", flush=True)
        result = retrieve_for_subsection(
            sub["name"], index, metadata,
            drhp_source=drhp_source,
            model=model,
        )
        top_score = result["data_chunks"][0]["score"] if result["data_chunks"] else 0.0
        print(f"confidence={result['confidence']}  top_score={top_score:.3f}", flush=True)
        results.append(result)

    return results
