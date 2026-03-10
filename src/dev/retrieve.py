"""
Stage 3: Retrieve

For each Business Overview subsection, retrieves the most relevant chunks
from the FAISS index using dual-query semantic search.

Subsection structure is inferred from the reference DRHP at runtime via
detect_subsections_from_drhp(). The hardcoded SUBSECTIONS list is the fallback
used when detection yields fewer than 3 headings.

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

import re
from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONF_HIGH   = 0.65
CONF_MEDIUM = 0.45
TOP_K_DATA  = 8   # data chunks per subsection (after dedup)
TOP_K_STYLE = 3   # style reference chunks per subsection

# Fallback: 10 hardcoded subsections used when DRHP detection fails
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

# Keywords used for fuzzy-matching detected headings to known subsections
_SUBSECTION_KEYWORDS: Dict[str, set] = {
    "Corporate History & Background":  {"history", "incorporation", "corporate", "established", "company", "background", "overview"},
    "Nature of Business & Products":   {"business", "products", "services", "nature", "offerings", "segments"},
    "Manufacturing & Operations":      {"manufacturing", "operations", "plant", "facility", "production", "facilities"},
    "Key Business Strengths":          {"strengths", "competitive", "advantages", "key", "differentiators"},
    "Promoters & Management":          {"promoters", "management", "directors", "promoter", "managerial"},
    "Subsidiaries & Associates":       {"subsidiaries", "associates", "group", "joint", "venture"},
    "Financial Highlights":            {"financial", "highlights", "revenue", "profit", "ebitda", "performance"},
    "Geographic Presence":             {"geographic", "presence", "regions", "states", "distribution", "network"},
    "Awards & Certifications":         {"awards", "certifications", "iso", "accreditation", "recognition"},
    "Future Strategy":                 {"strategy", "future", "growth", "expansion", "plans", "strategic"},
}


# ---------------------------------------------------------------------------
# DRHP-based subsection detection
# ---------------------------------------------------------------------------

def detect_subsections_from_drhp(
    metadata: List[Dict],
    drhp_source: str,
    min_subsections: int = 3,
) -> List[Dict]:
    """
    Detect Business Overview subsection headings from the reference DRHP chunks.

    Strategy:
    1. Find the chunk(s) in drhp_source that contain "BUSINESS OVERVIEW"
    2. Scan the following ~40 chunks for ALL-CAPS short lines (subsection headings)
    3. Fuzzy-match each heading to a known subsection (→ use its predefined queries)
       or treat it as novel (→ use heading words as queries, generic schema)
    4. Fall back to hardcoded SUBSECTIONS if fewer than min_subsections detected

    Returns:
        List of subsection dicts with keys: name, primary_query, secondary_query
    """
    drhp_chunks = sorted(
        [c for c in metadata if c.get("source") == drhp_source],
        key=lambda c: c.get("page", 0),
    )

    if not drhp_chunks:
        print("[retrieve] No reference DRHP chunks found — using default subsections", flush=True)
        return SUBSECTIONS

    # Locate the Business Overview section — skip TOC occurrences (lines with dot leaders)
    bo_keywords = {"business overview", "our business", "business description"}
    start_idx = None
    for i, chunk in enumerate(drhp_chunks):
        text = chunk.get("text", "")
        text_lower = text.lower()
        if any(kw in text_lower for kw in bo_keywords):
            # Prefer a non-TOC chunk: the matching line should not have dot leaders
            matching_lines = [
                ln for ln in text.splitlines()
                if any(kw in ln.lower() for kw in bo_keywords)
            ]
            is_toc = any(".." in ln for ln in matching_lines)
            if not is_toc:
                start_idx = i
                break
            # Keep as fallback if we find nothing better
            if start_idx is None:
                start_idx = i

    if start_idx is None:
        print("[retrieve] 'BUSINESS OVERVIEW' not found in reference DRHP — using default subsections", flush=True)
        return SUBSECTIONS

    # Scan up to 40 chunks after the Business Overview marker for headings
    scan_chunks = drhp_chunks[start_idx: start_idx + 40]
    heading_re  = re.compile(r'^[A-Z][A-Z\s&,\-\(\)\./\']{2,79}$')
    skip_words  = {"THE", "AND", "IN", "OF", "TO", "A", "AN", "FOR", "BY", "OR", "ON", "AT"}

    detected: List[str] = []
    for chunk in scan_chunks:
        for line in chunk.get("text", "").splitlines():
            line = line.strip()
            if (heading_re.match(line)
                    and ".." not in line          # skip TOC dot-leader lines
                    and line not in skip_words
                    and len(line.split()) >= 2
                    and line not in detected):
                detected.append(line)

    # Too few → detection missed the section; too many → probably scanned TOC or wrong chapter
    max_subsections = 15
    if len(detected) < min_subsections or len(detected) > max_subsections:
        print(
            f"[retrieve] {len(detected)} heading(s) detected from reference DRHP "
            f"(expected {min_subsections}–{max_subsections}) — using default subsections",
            flush=True,
        )
        return SUBSECTIONS

    print(
        f"[retrieve] Detected {len(detected)} subsection heading(s) from reference DRHP: "
        f"{detected}",
        flush=True,
    )

    # Map each detected heading to a subsection dict
    result = []
    seen_names = set()
    for heading in detected:
        matched = _fuzzy_match_subsection(heading)
        sub = matched if matched else _make_generic_subsection(heading)
        # Deduplicate: don't add the same canonical subsection twice
        if sub["name"] not in seen_names:
            seen_names.add(sub["name"])
            result.append(sub)

    return result


def _fuzzy_match_subsection(heading: str) -> Optional[Dict]:
    """
    Return the SUBSECTIONS entry whose keywords best overlap with the heading words.
    Returns None if no keyword overlaps at all.
    """
    words = set(heading.lower().split())
    best_sub, best_score = None, 0
    for sub in SUBSECTIONS:
        keywords = _SUBSECTION_KEYWORDS.get(sub["name"], set())
        score = len(words & keywords)
        if score > best_score:
            best_score, best_sub = score, sub
    return best_sub if best_score >= 1 else None


def _make_generic_subsection(heading: str) -> Dict:
    """Build a generic subsection dict for a novel heading not in SUBSECTIONS."""
    query = re.sub(r'\b(OUR|THE|AND|IN|OF)\b', '', heading).strip().lower()
    words = query.split()
    return {
        "name":            heading.title(),
        "primary_query":   query,
        "secondary_query": " ".join(words[:3]) if len(words) >= 3 else query,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_for_subsection(
    subsection_name: str,
    index,
    metadata: List[Dict],
    drhp_source: Optional[str] = None,
    model=None,
    _sub_dict: Optional[Dict] = None,
) -> Dict:
    """
    Retrieve data chunks and style chunks for a single subsection.

    Args:
        subsection_name: Display name for this subsection.
        index:           FAISS IndexFlatIP built in Stage 2.
        metadata:        Chunk metadata list in the same order as the index.
        drhp_source:     Basename of the reference DRHP, e.g. "sample_drhp.pdf".
                         Used to exclude data chunks and filter style chunks.
                         If None, style_chunks will be empty.
        model:           Pre-loaded SentenceTransformer. If None, loaded on demand.
        _sub_dict:       Pre-resolved subsection dict (name + queries). If None,
                         looked up from SUBSECTIONS; falls back to generic queries.

    Returns:
        {
            "subsection":        str,
            "data_chunks":       List[Dict],  # top-8, supporting docs only
            "style_chunks":      List[Dict],  # top-3, drhp_source only
            "confidence":        "high" | "medium" | "low",
            "low_confidence_flag": bool,
        }
    """
    from src.dev.embed import search

    # Resolve subsection queries
    if _sub_dict:
        sub = _sub_dict
    else:
        sub = next((s for s in SUBSECTIONS if s["name"] == subsection_name), None)
        if sub is None:
            # Novel subsection — use its name as the query
            query = subsection_name.lower()
            sub = {"name": subsection_name, "primary_query": query, "secondary_query": query}

    # --- Step 3.1 / 3.2: Dual query search ---
    fetch_k = TOP_K_DATA * 3 if drhp_source else TOP_K_DATA * 2
    primary_hits   = search(sub["primary_query"],   index, metadata, top_k=fetch_k, model=model)
    secondary_hits = search(sub["secondary_query"], index, metadata, top_k=fetch_k, model=model)

    # Deduplicate by chunk_id — exclude reference DRHP from data
    seen: Dict[str, Dict] = {}
    for chunk in primary_hits + secondary_hits:
        if drhp_source and chunk.get("source") == drhp_source:
            continue
        cid = chunk["chunk_id"]
        if cid not in seen or chunk["score"] > seen[cid]["score"]:
            seen[cid] = chunk

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
    Detect subsection structure from the reference DRHP, then retrieve for each.

    Falls back to hardcoded SUBSECTIONS if detection yields fewer than 3 headings
    or if drhp_source is not provided.

    Loads the embedding model once and reuses it across all subsection queries.
    """
    from src.dev.embed import _load_model

    if model is None:
        model = _load_model()

    # Infer subsection list from reference DRHP (or fall back to hardcoded)
    if drhp_source:
        active_subsections = detect_subsections_from_drhp(metadata, drhp_source)
    else:
        active_subsections = SUBSECTIONS
        print("[retrieve] No drhp_source provided — using default subsections", flush=True)

    results = []
    for sub in active_subsections:
        print(f"[retrieve] {sub['name']} ...", end=" ", flush=True)
        result = retrieve_for_subsection(
            sub["name"], index, metadata,
            drhp_source=drhp_source,
            model=model,
            _sub_dict=sub,
        )
        top_score = result["data_chunks"][0]["score"] if result["data_chunks"] else 0.0
        print(f"confidence={result['confidence']}  top_score={top_score:.3f}", flush=True)
        results.append(result)

    return results
