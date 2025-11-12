from typing import Mapping, Any, Dict, Union

from chat_worker import settings
from chat_worker.application.rag.retrievers.base import RagContext
from chat_worker.settings import WeaviateSearchType

"""
RAG helper utilities.

This module contains small, stateless helpers used by retrievers and the RAG pipeline.
They are grouped by responsibility and kept side‑effect free.
Docstrings follow a concise, imperative style; behavior is unchanged from the previous version.
"""

# =====================================================================
# Logging / Diagnostics
# =====================================================================

def log_items(items, logger, label: str = "[RAG]", limit: int = 10) -> None:
    """
    Log retrieval diagnostics for a short list of items.

    Args:
        items: Iterable of retrieval results (Weaviate objects or similar) that may have
               `metadata.score`, `metadata.distance`, and `properties.filename`.
        logger: Logger instance to use (e.g., logging.getLogger(...)).
        label: Text prefix prepended to each line (e.g., "[RAG][hybrid]").
        limit: Maximum number of items to log.
    """
    for i, o in enumerate(items[:limit]):
        md = getattr(o, "metadata", None)
        s = getattr(md, "score", None)
        d = getattr(md, "distance", None)
        props = getattr(o, "properties", {}) or {}
        fn = props.get("filename")
        logger.info(f"{label} #{i} score={s} dist={d} file={fn}")


# =====================================================================
# Context wiring (shared across retrievers)
# =====================================================================

def resolve_context(ctx: RagContext, top_k: int | None, filters: Mapping[str, Any] | None):
    """
    Unpack commonly used context parts and normalize inputs.

    Returns:
        (client, collection_name, text_key, k, normalized_filters)
    """
    client = ctx.client
    collection_name = ctx.collection
    text_key = getattr(ctx, "text_key", "text")
    k = int(top_k or getattr(ctx, "default_top_k", 6) or 6)
    nf = normalize_filters(dict(filters) if filters else None)
    return client, collection_name, text_key, k, nf


# =====================================================================
# Filter / Search‑type normalization
# =====================================================================

def normalize_filters(filters: Dict[str, Any] | None):
    """
    Convert app‑level filters into Weaviate `where` format.

    Rules:
      - Strings → case‑insensitive partial matching via `TextContains`.
      - Numbers/bools → `Equal` with the corresponding value type.
      - Lists → OR of each item following the rules above.

    Returns:
        A dict usable as Weaviate `where` or None if no filters.
    """
    if not filters:
        return None
    ops = []
    for k, v in filters.items():
        if isinstance(v, list):
            sub = []
            for item in v:
                if isinstance(item, bool):
                    sub.append({"path": [k], "operator": "Equal", "valueBoolean": item})
                elif isinstance(item, (int, float)):
                    sub.append({"path": [k], "operator": "Equal", "valueNumber": item})
                else:
                    sub.append({
                        "path": [k],
                        "operator": "TextContains",  # case‑insensitive partial match
                        "valueText": str(item).lower(),
                    })
            ops.append({"operator": "Or", "operands": sub})
        elif isinstance(v, bool):
            ops.append({"path": [k], "operator": "Equal", "valueBoolean": v})
        elif isinstance(v, (int, float)):
            ops.append({"path": [k], "operator": "Equal", "valueNumber": v})
        else:
            ops.append({
                "path": [k],
                "operator": "TextContains",  # case‑insensitive partial match
                "valueText": str(v).lower(),
            })
    return {"operator": "And", "operands": ops} if len(ops) > 1 else (ops[0] if ops else None)


def normalize_search_type(x: Union[WeaviateSearchType, str, None], fb: WeaviateSearchType) -> WeaviateSearchType:
    """
    Normalize a user‑provided search type to a WeaviateSearchType enum.
    """
    if x is None:
        return fb
    return x if isinstance(x, WeaviateSearchType) else WeaviateSearchType(str(x).lower())


# =====================================================================
# Query normalization / tokenization
# =====================================================================

def normalize_query(q: str, *, mode: str = "full") -> str:
    """
    Normalize a natural‑language query.

    Modes:
      - full: NFC normalize, apply Korean tech aliases, lowercase,
              add boundaries between Hangul and ASCII/digits,
              strip punctuation, collapse whitespace.
      - light: NFC normalize, aliases, lowercase, keep dashes, light cleanup.
    """
    import re, unicodedata
    if q is None:
        return ""
    q = unicodedata.normalize("NFC", str(q))
    q = ko_tech_aliases(q)
    if mode == "full":
        q = q.lower()
        q = re.sub(r'([가-힣])([a-z0-9])', r'\1 \2', q)
        q = re.sub(r'([a-z0-9])([가-힣])', r'\1 \2', q)
        q = q.replace("-", " ")
        q = re.sub(r"[^\w\s]", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q
    elif mode == "light":
        q = q.lower()
        q = re.sub(r"[^\w\s-]", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q
    else:
        return q


def ko_tech_aliases(q: str) -> str:
    """
    Normalize common Korean technical terms to English acronyms
    (e.g., '챗지피티' → 'chatgpt', '엘엘엠' → 'llm').
    """
    import re
    s = q
    rep = [
        (r"(챗|쳇)\s*지\s*피\s*티", "chatgpt"),
        (r"(지|쥐)\s*피\s*티", "gpt"),
        (r"엘엘엠|엘\s*엘\s*엠", "llm"),
        (r"에이\s*아이", "ai"),
        (r"에이\s*피\s*아이", "api"),
        (r"유\s*아이", "ui"),
        (r"디\s*비", "db"),
        (r"에스\s*큐\s*엘", "sql"),
        (r"제이\s*에스\s*온|제이슨", "json"),
        (r"피\s*디\s*에프", "pdf"),
        (r"시\s*에스\s*브이", "csv"),
        (r"유\s*알\s*엘", "url"),
        (r"에이\s*더블유\s*에스|아마존\s*웹\s*서비스", "aws"),
    ]
    for pat, to in rep:
        s = re.sub(pat, to, s, flags=re.IGNORECASE)
    return s


def kw_tokens(q: str) -> list[str]:
    """
    Extract ASCII/Korean tokens for lightweight keyword checks.

    Returns lowercase tokens with stopwords removed.
    """
    import re
    nq = normalize_query(q)
    ascii_words = re.findall(r"[a-z0-9]{2,}", nq)
    korean_words = re.findall(r"[가-힣]{2,}", nq)
    toks = ascii_words + korean_words
    try:
        stops = getattr(settings, "ko_stop_tokens", None) or []
    except Exception:
        stops = []
    stopset = {str(s).strip().lower() for s in stops if s}
    toks = [t for t in toks if t.lower() not in stopset]
    return toks


def kw_tokens_split(q: str) -> tuple[list[str], list[str]]:
    """
    Extract tokens and a rarer subset after stopword filtering.

    Returns:
        (all_tokens, rare_tokens)
        Rare = ASCII len ≥ 4 or Korean len ≥ 3
    """
    import re
    nq = normalize_query(q)
    ascii_words = re.findall(r"[a-z0-9]{3,}", nq)
    korean_words = re.findall(r"[가-힣]{2,}", nq)
    try:
        stops = getattr(settings, "ko_stop_tokens", None) or []
    except Exception:
        stops = []
    stopset = {str(s).strip().lower() for s in stops if s}
    ascii_words = [w for w in ascii_words if w.lower() not in stopset]
    korean_words = [h for h in korean_words if h.lower() not in stopset]
    toks = [*ascii_words, *korean_words]
    rare_ascii = [w for w in ascii_words if len(w) >= 4]
    rare_korean = [h for h in korean_words if len(h) >= 3]
    rare = rare_ascii + rare_korean
    return toks, rare


# =====================================================================
# Matching / scoring helpers
# =====================================================================

def count_hits(toks: list[str], text: str) -> int:
    """
    Count total occurrences of tokens in the given text (case‑insensitive).
    """
    if not toks or not text:
        return 0
    low = text.lower()
    return sum(low.count((t or "").lower()) for t in toks if t)


def kw_hit(toks: list[str], d) -> bool:
    """
    Return True if any token appears in document text/metadata/filename (substring match).
    """
    try:
        meta = getattr(d, "metadata", {}) or {}
        txt = (getattr(d, "page_content", "") or "")
        fname = meta.get("filename") or ""
        fname_kw = meta.get("filename_kw") or ""
        blob = f"{txt} {fname} {fname_kw}".lower()
        return any((t or "").lower() in blob for t in toks)
    except Exception:
        return False


# =====================================================================
# Snippet extraction
# =====================================================================

def extract_snippets(toks: list[str], text: str, *, max_len: int = 320, max_snippets: int = 4) -> list[str]:
    """
    Extract context snippets around token hits; fall back to the head of the text if no hits.

    Behavior:
      - Find token hit positions (case‑insensitive).
      - Build windows around hits and merge overlaps.
      - Trim lightly to sentence boundaries when possible.
    """
    import re
    if not text:
        return []
    low = text.lower()
    # Find hit positions for any token
    hits = []
    for t in toks:
        if not t:
            continue
        for m in re.finditer(re.escape(t.lower()), low):
            hits.append(m.start())
    # If no explicit hits, return first chunkish snippet
    if not hits:
        head = text.strip().splitlines()
        if head:
            head_text = " ".join(head[:3])[: max_len]
            return [head_text]
        return [text[: max_len]]
    # Build windows around hits, merge overlapping regions
    hits = sorted(hits)
    windows = []
    half = max_len // 2
    for pos in hits:
        start = max(0, pos - half)
        end = min(len(text), pos + half)
        if windows and start <= windows[-1][1] + 10:
            # merge with previous
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    # Extract up to max_snippets windows, trimmed to sentence boundaries if possible
    out: list[str] = []
    for (s, e) in windows[: max_snippets]:
        chunk = text[s:e]
        # light sentence boundary trim
        left = max(chunk.find(". "), chunk.find("\n"))
        right = max(chunk.rfind(". "), chunk.rfind("\n"))
        if 0 < left < len(chunk) - 1:
            chunk = chunk[left + 1:]
        if 0 < right < len(chunk) - 1:
            chunk = chunk[: right + 1]
        out.append(chunk.strip())
    return out