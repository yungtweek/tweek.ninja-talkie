from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from index_worker.domain.entities import Chunk

logger = logging.getLogger("WeaviateVectorRepo")

# --- Optional / lazy import --------------------------------------------------
try:
    import weaviate  # type: ignore
    from weaviate import Client as WeaviateClientV3  # v3 compat
    try:
        # v4 layout (preferred)
        from weaviate import connect_to_custom
        from weaviate.collections import Collection
        from weaviate.classes import query as wq
        V4 = True
    except Exception:  # pragma: no cover - when client is v3
        V4 = False
except Exception as e:  # pragma: no cover
    weaviate = None
    WeaviateClientV3 = None  # type: ignore
    V4 = False
    logger.warning("weaviate client not installed: %s", e)


# --- Helpers -----------------------------------------------------------------

def _chunk_identity(
    chunk: Union[Dict[str, Any], Any]
) -> Tuple[str, str, str]:
    """
    Return (user_id, file_id, chunk_id) from a chunk.
    Supports both dict-based chunks and Chunk class instances.
    For dicts: robust against nested metadata.
    For Chunk instances: uses attributes directly.
    """
    # Import here to avoid circular import at module level
    try:
        from index_worker.domain.entities import Chunk
    except ImportError:
        Chunk = None  # type: ignore

    if Chunk is not None and isinstance(chunk, Chunk):
        # Handle Chunk class instance
        meta = getattr(chunk, "meta", {}) or {}
        user_id = str(
            getattr(chunk, "user_id", None)
            or meta.get("owner_id")
            or meta.get("user_id")
            or ""
        )
        file_id = str(
            getattr(chunk, "file_id", None)
            or getattr(chunk, "fileId", None)
            or meta.get("file_id")
            or meta.get("fileId")
            or ""
        )
        chunk_id = str(getattr(chunk, "chunk_id", None) or getattr(chunk, "id", None) or "")
    else:
        # Fallback: dict-based chunk (legacy)
        md = chunk.get("metadata") or {}
        user_id = str(
            chunk.get("user_id")
            or md.get("owner_id")
            or md.get("user_id")
            or ""
        )
        file_id = str(
            chunk.get("file_id")
            or chunk.get("fileId")
            or md.get("file_id")
            or md.get("fileId")
            or ""
        )
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "")
    if not user_id or not file_id or not chunk_id:
        raise ValueError("chunk must include user_id, file_id, chunk_id/id")
    return user_id, file_id, chunk_id


def _chunk_props(chunk: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    """Map our chunk (dict or Chunk instance) to weaviate properties."""
    # Import here to avoid circular import at module level
    try:
        from index_worker.domain.entities import Chunk as ChunkEntity
    except ImportError:
        ChunkEntity = None  # type: ignore

    if ChunkEntity is not None and isinstance(chunk, ChunkEntity):
        meta: Dict[str, Any] = getattr(chunk, "meta", {}) or {}
        user_id = str(meta.get("user_id") or meta.get("owner_id") or "")
        file_id = str(getattr(chunk, "document_id", "") or meta.get("file_id") or meta.get("fileId") or "")
        chunk_id = str(getattr(chunk, "id", ""))
        filename = meta.get("filename")

        # text can be a ChunkText value object
        text_val = getattr(chunk, "text", None)
        if hasattr(text_val, "text"):
            text_val = text_val.text

        # page is optional and may be string in meta
        page_raw = meta.get("page")
        page = int(page_raw) if isinstance(page_raw, (int, str)) and str(page_raw).isdigit() else None

        return {
            "user_id": user_id,
            "file_id": file_id,
            "chunk_id": chunk_id,
            "filename": filename,
            "text": text_val,
            "chunk_index": int(getattr(chunk, "order", 0)),
            "page": page,
        }

    # Fallback: legacy dict-based chunk
    md: Dict[str, Any] = chunk.get("metadata") or {}
    user_id = str(
        chunk.get("user_id")
        or md.get("owner_id")
        or md.get("user_id")
        or ""
    )
    file_id = str(
        chunk.get("file_id")
        or chunk.get("fileId")
        or md.get("file_id")
        or md.get("fileId")
        or ""
    )
    chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "")
    filename = chunk.get("filename") or md.get("filename")
    text_val = chunk.get("text") or md.get("text")
    chunk_index = int(chunk.get("index") or chunk.get("chunk_index") or md.get("chunk_index") or 0)
    page_raw = chunk.get("page") or md.get("page")
    page = int(page_raw) if isinstance(page_raw, (int, str)) and str(page_raw).isdigit() else None

    return {
        "user_id": user_id,
        "file_id": file_id,
        "chunk_id": chunk_id,
        "filename": filename,
        "text": text_val,
        "chunk_index": chunk_index,
        "page": page,
    }


# --- Repository --------------------------------------------------------------
class WeaviateVectorRepository:
    """
    Minimal Weaviate vector repository implementing upsert semantics for chunks.

    Supports v4 client (collections API) and falls back to v3 schema/objects API.
    """

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection: str = "Chunks",
        batch_size: int = 64,
        timeout: int = 30,
    ) -> None:
        self.url = url or os.getenv("WEAVIATE_URL", "http://localhost:8080")
        self.api_key = api_key or os.getenv("WEAVIATE_API_KEY")
        self.collection_name = collection
        self.batch_size = batch_size
        self.timeout = timeout

        if weaviate is None:
            raise RuntimeError("weaviate client is not installed")

        if V4:
            # v4 connect
            self._client_v4 = connect_to_custom(
                http_host="localhost",
                http_port=8080,
                http_secure=False,
                grpc_host="localhost",
                grpc_port=50051,
                grpc_secure=False,
                # additional_config=AdditionalConfig(timeout.self.timeout),
                # auth_credentials=weaviate.auth.AuthApiKey(self.api_key) if self.api_key else None,
            )
            self._collection_v4 = self._ensure_collection_v4(self.collection_name)
            self._client_v3 = None
        else:
            # v3 client
            self._client_v4 = None
            self._collection_v4 = None
            self._client_v3 = WeaviateClientV3(self.url, auth_client_secret=weaviate.AuthApiKey(self.api_key) if self.api_key else None)  # type: ignore
            self._ensure_schema_v3(self.collection_name)

    # --- v4 schema -----------------------------------------------------------
    def _ensure_collection_v4(self, name: str):  # -> Collection
        assert self._client_v4 is not None
        try:
            if name not in self._client_v4.collections.list_all():
                self._client_v4.collections.create(
                    name,
                    description="RAG chunks",
                    vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                    properties=[
                        weaviate.classes.config.Property(name="user_id", data_type=weaviate.classes.config.DataType.TEXT),
                        weaviate.classes.config.Property(name="file_id", data_type=weaviate.classes.config.DataType.TEXT),
                        weaviate.classes.config.Property(name="chunk_id", data_type=weaviate.classes.config.DataType.TEXT),
                        weaviate.classes.config.Property(name="filename", data_type=weaviate.classes.config.DataType.TEXT),
                        weaviate.classes.config.Property(name="text", data_type=weaviate.classes.config.DataType.TEXT),
                        weaviate.classes.config.Property(name="chunk_index", data_type=weaviate.classes.config.DataType.INT),
                        weaviate.classes.config.Property(name="page", data_type=weaviate.classes.config.DataType.INT),
                    ],
                )
        except Exception as e:  # pragma: no cover
            logger.warning("ensure v4 collection failed (might already exist): %s", e)
        return self._client_v4.collections.get(name)

    # --- v3 schema -----------------------------------------------------------
    def _ensure_schema_v3(self, name: str) -> None:
        assert self._client_v3 is not None
        try:
            schema = self._client_v3.schema.get()  # type: ignore[attr-defined]
            classes = {c.get("class") for c in schema.get("classes", [])}
            if name not in classes:
                self._client_v3.schema.create_class({  # type: ignore[attr-defined]
                    "class": name,
                    "vectorizer": "none",
                    "properties": [
                        {"name": "user_id", "dataType": ["text"]},
                        {"name": "file_id", "dataType": ["text"]},
                        {"name": "chunk_id", "dataType": ["text"]},
                        {"name": "filename", "dataType": ["text"]},
                        {"name": "text", "dataType": ["text"]},
                        {"name": "chunk_index", "dataType": ["int"]},
                        {"name": "page", "dataType": ["int"]},
                    ],
                })
        except Exception as e:  # pragma: no cover
            logger.warning("ensure v3 schema failed (might already exist): %s", e)

    # --- Public API ----------------------------------------------------------
    async def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length mismatch")
        if not chunks:
            return

        if V4:
            await self._upsert_v4(chunks, vectors)
        else:
            await self._upsert_v3(chunks, vectors)

    async def delete_by_user_file(self, user_id: str, file_id: str) -> int:
        """
        Delete all chunk objects for a given (user_id, file_id) pair.
        Returns the number of deleted objects (best-effort based on client response).
        """
        if not user_id or not file_id:
            raise ValueError("user_id and file_id are required")

        try:
            if V4:
                return await self._delete_v4(user_id, file_id)
            else:
                return await self._delete_v3(user_id, file_id)
        except Exception as e:
            logger.error("delete_by_user_file failed for user_id=%s file_id=%s: %s", user_id, file_id, e)
            raise

# --- v4 delete -----------------------------------------------------------
    async def _delete_v4(self, user_id: str, file_id: str) -> int:
        assert self._collection_v4 is not None
        # Build filter: user_id == ... AND file_id == ...
        where = (wq.Filter.by_property("user_id").equal(user_id) & wq.Filter.by_property("file_id").equal(file_id))
        try:
            res = self._collection_v4.data.delete_many(where=where)
            # v4 returns an object with "matches" (count) in most versions
            # fallbacks included for forward/backward compat
            if isinstance(res, dict):
                return int(res.get("matches") or res.get("count") or 0)
            # Some client versions return a dataclass-like object with attributes
            for key in ("matches", "count"):
                if hasattr(res, key):
                    val = getattr(res, key)
                    if isinstance(val, int):
                        return val
            return 0
        except Exception as e:
            logger.error("v4 delete_many failed for user_id=%s file_id=%s: %s", user_id, file_id, e)
            raise

# --- v3 delete -----------------------------------------------------------
    async def _delete_v3(self, user_id: str, file_id: str) -> int:
        assert self._client_v3 is not None
        name = self.collection_name
        # GraphQL-style where filter for v3
        where = {
            "operator": "And",
            "operands": [
                {"path": ["user_id"], "operator": "Equal", "valueString": str(user_id)},
                {"path": ["file_id"], "operator": "Equal", "valueString": str(file_id)},
            ],
        }
        try:
            res = self._client_v3.batch.delete_objects(class_name=name, where=where)  # type: ignore[attr-defined]
            # Typical v3 response: {"results": {"matches": N, "limit": ...}}
            if isinstance(res, dict):
                results = res.get("results") or {}
                return int(results.get("matches") or results.get("successful") or 0)
            return 0
        except Exception as e:
            logger.error("v3 delete_objects failed for user_id=%s file_id=%s: %s", user_id, file_id, e)
            raise

    # --- v4 upsert -----------------------------------------------------------
    async def _upsert_v4(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        assert self._collection_v4 is not None
        logger.debug("v4 upsert %d chunks", len(chunks))
        # v4 supports insert_many; we emulate upsert by using id=chunk_id
        batch: List[Dict[str, Any]] = []
        ids: List[str] = []
        vecs: List[List[float]] = []

        for ch, vec in zip(chunks, vectors):
            props = _chunk_props(ch)
            _uid, _fid, cid = _chunk_identity(ch)
            batch.append(props)
            ids.append(cid)
            vecs.append(list(vec))

            if len(batch) >= self.batch_size:
                # Per-item insert for broad v4 compatibility (vectors passed here)
                for _props, _vec, _id in zip(batch, vecs, ids):
                    try:
                        self._collection_v4.data.insert(properties=_props, vector=_vec)
                    except Exception as ie:
                        logger.error("v4 per-item insert failed for %s: %s", ie)
                batch, vecs, ids = [], [], []

        if batch:
            for _props, _vec, _id in zip(batch, vecs, ids):
                try:
                    self._collection_v4.data.insert(properties=_props, vector=_vec)
                except Exception as ie:
                    logger.error("v4 per-item insert failed for %s: %s",  ie)

    # --- v3 upsert -----------------------------------------------------------
    async def _upsert_v3(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        assert self._client_v3 is not None
        name = self.collection_name
        with self._client_v3.batch(batch_size=self.batch_size) as batch:  # type: ignore[attr-defined]
            for ch, vec in zip(chunks, vectors):
                props = _chunk_props(ch)
                _uid, _fid, cid = _chunk_identity(ch)
                # Weaviate v3: use add_data_object with uuid to emulate upsert (replace-on-conflict not native)
                try:
                    batch.add_data_object(
                        data_object=props,
                        class_name=name,
                        uuid=cid,
                        vector=list(vec),
                    )
                except Exception as e:  # pragma: no cover
                    logger.warning("v3 batch add failed for %s: %s", cid, e)
    # --- Cleanup -------------------------------------------------------------
    async def close(self) -> None:
        logger.debug("closing weaviate client")
        """Gracefully close any underlying Weaviate client connections."""
        try:
            if V4 and self._client_v4 is not None:
                try:
                    # v4 connection has a .close() or .__aexit__ handler
                    close_fn = getattr(self._client_v4, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception as e:
                    logger.warning("failed to close weaviate v4 client: %s", e)

            if not V4 and self._client_v3 is not None:
                try:
                    close_fn = getattr(self._client_v3, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception as e:
                    logger.warning("failed to close weaviate v3 client: %s", e)

        except Exception as e:
            logger.warning("unexpected error during weaviate client close: %s", e)