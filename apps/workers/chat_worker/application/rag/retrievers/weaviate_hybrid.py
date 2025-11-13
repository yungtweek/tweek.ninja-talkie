from logging import getLogger
from typing import Any, Mapping, Sequence

import weaviate.classes as wvc
from chat_worker.application.rag.document import items_to_docs
from chat_worker.application.rag.helpers import log_items, resolve_context, normalize_query, kw_tokens_split
from chat_worker.application.rag.retrievers.base import BaseRetriever, RagContext, RetrieveResult

logger = getLogger("WeaviateHybridRetriever")


class WeaviateHybridRetriever(BaseRetriever):
    """
    Hybrid retriever (vector + BM25) with dynamic alpha and keyword guards.

    Stateless implementation: all runtime dependencies are provided via RagContext.
    """
    name = "weaviate_hybrid"

    def __init__(self, ctx: RagContext):
        super().__init__(ctx)
        self._ctx = ctx


    # ---------- small helpers (stateless) ----------
    @staticmethod
    def _kw_guard(nq_tokens: list[str], props: dict, *, text_key: str) -> bool:
        """Return True if any token appears in text/body or filename fields."""
        if not nq_tokens or not props:
            return False
        txt_fields = [
            props.get(text_key) or "",
            props.get("text_tri") or "",
            props.get("filename") or "",
            props.get("filename_kw") or "",
        ]
        blob = " ".join(txt_fields).lower()
        return any((t or "").lower() in blob for t in nq_tokens)

    @staticmethod
    def _text_hit_only(props: dict, tokens: list[str], *, text_key: str) -> bool:
        """Check tokens against text/body fields (text + tri + filename variants)."""
        txt = (props.get(text_key) or "")
        tri = (props.get("text_tri") or "")
        filename = (props.get("filename") or "") + " " + (props.get("filename_kw") or "")
        blob = f"{txt} {tri} {filename}".lower()
        return any(t and t.lower() in blob for t in tokens)

    # ---------- main API ----------
    def invoke(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> RetrieveResult | list:
        """
        Execute hybrid retrieval using Weaviate Collections API.

        Args:
            query: raw user query
            top_k: optional override of result size
            filters: optional backend filters

        Returns:
            RetrieveResult (if Base layer wraps results) or list[Document] for backward compatibility.
        """
        ctx = getattr(self, "_ctx", None)
        if ctx is None:
            raise ValueError("RagContext is not set. Initialize WeaviateHybridRetriever with ctx=RagContext.")

        # Pull dependencies from context (stateless retriever)
        client, collection_name, text_key, k, nf = resolve_context(ctx, top_k, filters)
        embeddings = ctx.embeddings
        base_alpha_ctx = float(getattr(ctx, "alpha", 0.5) or 0.5)
        s = getattr(ctx, "settings", None)

        if client is None or not hasattr(client, "collections"):
            raise ValueError("Weaviate >=1.0 Collections API required for hybrid")

        coll = client.collections.use(collection_name)
        vec = embeddings.embed_query(query)
        nq = normalize_query(query)
        nq_tokens, rare_tokens = kw_tokens_split(query)

        # ---- Alpha policy knobs from settings (fall back to sane defaults) ----
        def _get(name: str, default: float) -> float:
            try:
                val = getattr(s, name) if s is not None else None
                return float(val) if val is not None else float(default)
            except Exception:
                return float(default)

        alpha_base_default = float(base_alpha_ctx)
        alpha_multi_strong_max = _get("alpha_multi_strong_max", 0.45)  # cap keyword weight when multi-strong hits
        alpha_single_strong_min = _get("alpha_single_strong_min", 0.55)  # cap in single-strong cases
        alpha_weak_hit_min = _get("alpha_weak_hit_min", 0.30)            # weak BM25 → vector-heavy
        alpha_no_bm25_min = _get("alpha_no_bm25_min", 0.10)              # no BM25 → almost pure vector

        # ---- (1) BM25 preflight to probe keyword strength (body-only) ----
        bm25_hits = 0
        bm25_hits_strong = 0
        strong_files: set[str] = set()
        try:
            # Try compound variants from optional pipeline-style expander if present in ctx
            queries: Sequence[str] = [query]

            bm25_hits_text_total = 0
            for sub in queries:
                nqs = normalize_query(sub, mode="light")
                probe = coll.query.bm25(
                    query=nqs,
                    limit=min(k, 3),  # light preflight
                    query_properties=[text_key, "text_tri", "filename", "filename_kw"],
                    return_metadata=wvc.query.MetadataQuery(score=True),
                    return_properties=[text_key, "text_tri", "filename", "filename_kw", "chunk_index"],
                )
                objs = list(probe.objects or [])
                for o in objs:
                    props = getattr(o, "properties", {}) or {}
                    md = getattr(o, "metadata", None)
                    try:
                        sc = float(getattr(md, "score", 0.0) or 0.0)
                    except Exception:
                        sc = 0.0
                    if self._text_hit_only(props, nq_tokens, text_key=text_key):
                        bm25_hits_text_total += 1
                    # Strong hit = rare-token + decent BM25 score
                    if sc >= 0.60 and self._text_hit_only(props, rare_tokens, text_key=text_key):
                        bm25_hits_strong += 1
                        fname = props.get("filename") or "unknown"
                        strong_files.add(fname)
            bm25_hits = bm25_hits_text_total
        except Exception:
            bm25_hits = 0
            bm25_hits_strong = 0
            strong_files = set()

        # ---- (2) Dynamic alpha & guard policy ----
        base_alpha = float(kwargs.get("alpha", alpha_base_default))
        multi_file_strong = len(strong_files) >= 2
        if multi_file_strong:
            hit_type = "multi_file_strong"
            alpha_eff = min(float(base_alpha), alpha_multi_strong_max)
            guard_on = True
        elif bm25_hits_strong > 0:
            hit_type = "bm25_strong"
            alpha_eff = min(float(base_alpha), alpha_single_strong_min)
            guard_on = False
        elif bm25_hits > 0:
            hit_type = "bm25_only"
            alpha_eff = min(float(base_alpha), alpha_weak_hit_min)
            guard_on = False
        else:
            hit_type = "no_bm25"
            alpha_eff = min(float(base_alpha), alpha_no_bm25_min)
            guard_on = False

        logger.info(f"[RAG][hybrid] type={hit_type} alpha={alpha_eff} guard={guard_on} nq_tokens={nq_tokens} nq={nq}")

        # ---- (3) Main hybrid query ----
        try:
            res = coll.query.hybrid(
                query=nq,
                vector=vec,
                alpha=alpha_eff,
                limit=k,
                filters=nf,
                query_properties=[text_key, "text_tri", "filename", "filename_kw"],
                # Prefer RANKED; RELATIVE_SCORE can be toggled if needed:
                fusion_type=wvc.query.HybridFusion.RANKED,
                return_metadata=wvc.query.MetadataQuery(score=True, distance=True, explain_score=True),
                return_properties=["filename", "page", "chunk_index", "user_id", "file_id", "chunk_id", text_key],
            )
            raw_items = list(res.objects or [])
        except Exception as e:
            logger.info(f"[RAG] hybrid error: {e}")
            return []

        # ---- (4) Penalize filename-only matches when guard is ON ----
        if guard_on:
            for o in raw_items:
                props = getattr(o, "properties", {}) or {}
                md = getattr(o, "metadata", None)
                try:
                    dist = float(getattr(md, "distance", None) or 1.0)
                except Exception:
                    dist = 1.0
                hit_text = self._text_hit_only(props, rare_tokens, text_key=text_key)
                hit_file_only = (not hit_text) and self._kw_guard(rare_tokens, {"filename": props.get("filename", ""), "filename_kw": props.get("filename_kw", "")}, text_key=text_key)
                if hit_file_only:
                    try:
                        setattr(md, "distance", dist + 0.04)
                    except Exception:
                        pass

        # ---- (5) Distance cutoff ----
        dist_cut = (0.42 if guard_on else (0.32 if rare_tokens else 0.34))
        dist_kept = []
        for o in raw_items:
            md = getattr(o, "metadata", None)
            dist = getattr(md, "distance", None)
            try:
                if dist is None or float(dist) <= dist_cut:
                    dist_kept.append(o)
            except Exception:
                dist_kept.append(o)
        logger.info(f"[RAG][hybrid] dist_cut={dist_cut} dist_kept={len(dist_kept)}")

        # ---- (6) Keyword guard: require at least one rare-token hit when guard_on ----
        if guard_on:
            guarded = []
            for o in dist_kept:
                props = getattr(o, "properties", {}) or {}
                if self._kw_guard(rare_tokens, props, text_key=text_key):
                    guarded.append(o)
            items = guarded or dist_kept
        else:
            items = dist_kept

        # ---- (7) Vector-first re-rank: distance asc, score desc ----
        try:
            def _get_dist(obj):
                meta_obj = getattr(obj, "metadata", None)
                dist_val = getattr(meta_obj, "distance", None)
                try:
                    return float(dist_val) if dist_val is not None else 1.0
                except Exception:
                    return 1.0

            def _get_score(obj):
                meta_obj = getattr(obj, "metadata", None)
                score_val = getattr(meta_obj, "score", None)
                try:
                    return float(score_val) if score_val is not None else 0.0
                except Exception:
                    return 0.0

            items = sorted(items, key=lambda obj: (_get_dist(obj), -_get_score(obj)))
        except Exception:
            pass

        # ---- (8) Final topic guard: if no kept item hits tokens, fallback to near_text ----
        try:
            kw_hits_final = 0
            for _o in items:
                _props = getattr(_o, "properties", {}) or {}
                if self._kw_guard(rare_tokens, _props, text_key=text_key):
                    kw_hits_final += 1
        except Exception:
            kw_hits_final = 0

        if kw_hits_final == 0:
            logger.info(f"[RAG][hybrid] drop_all: no keyword hit → fallback to near_text")
            try:
                res2 = coll.query.near_text(
                    query=query,
                    distance=0.7,
                    limit=k,
                    filters=nf,
                    return_metadata=wvc.query.MetadataQuery(score=True, distance=True),
                    return_properties=["filename", "page", "chunk_index", "user_id", "file_id", "chunk_id", text_key],
                )
                docs = items_to_docs(list(res2.objects or []), text_key)
                return RetrieveResult(docs=docs, query=query, top_k=k, filters=dict(filters) if filters else None)
            except Exception:
                    return []

        log_items(items, logger)


        docs = items_to_docs(items, text_key)
        return RetrieveResult(docs=docs, query=query, top_k=k, filters=dict(filters) if filters else None)
