import json
from typing import Optional


# --- Helper functions for extracting and casting values ---
def _pick(d: dict, *keys: str, default=None):
    """Return the first non-empty/non-None value among keys from dict d."""
    for k in keys:
        if k is None:
            continue
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default

def _as_int(val, default=None):
    """Best-effort int casting for int/float/str; returns default if it fails."""
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        try:
            return int(val)
        except Exception:
            return default
    if isinstance(val, str):
        try:
            return int(val) if val.strip().lstrip("+-").isdigit() else default
        except Exception:
            return default
    return default


class Document:
    """
    Canonical document model used across Talkie RAG.
    This mirrors what we actually pass around in workers and UI:
      - ids & linkage: id(weaviate uuid), file_id, user_id
      - file info: title, filename, extension, file_size, labels, source, uri
      - chunk info: chunk_id, chunk_index, page
      - text: page_content, snippet
      - scores: score, distance, explain_score, score_contrast
      - free-form: meta, metadata
    """

    def __init__(
        self,
        *,
        doc_id: Optional[str] = None,
        file_id: Optional[str] = None,
        user_id: Optional[str] = None,
        title: str = "",
        filename: str = "",
        extension: str = "",
        file_size: int = 0,
        labels: list | None = None,
        source: str = "",
        uri: Optional[str] = None,
        # chunk related
        chunk_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        page: Optional[int] = None,
        # text
        page_content: str = "",
        snippet: Optional[str] = None,
        # scores
        score: Optional[float] = None,
        distance: Optional[float] = None,
        explain_score: Optional[str] = None,
        score_contrast: Optional[float] = None,
        # misc
        meta: dict | None = None,
        metadata: dict | None = None,
    ):
        self.doc_id = doc_id
        self.file_id = file_id
        self.user_id = user_id

        self.title = title
        self.filename = filename
        self.extension = extension
        self.file_size = file_size
        self.labels = labels if labels is not None else []
        self.source = source
        self.uri = uri

        self.chunk_id = chunk_id
        self.chunk_index = chunk_index
        self.page = page

        self.page_content = page_content
        self.snippet = snippet

        self.score = score
        self.distance = distance
        self.explain_score = explain_score
        self.score_contrast = score_contrast

        self.meta = meta if meta is not None else {}
        self.metadata = metadata if metadata is not None else {}

    @property
    def content(self):
        return self.page_content

    def __repr__(self):
        return (
            f"Document(title={self.title!r}, doc_id={self.doc_id!r}, file_id={self.file_id!r}, "
            f"len={len(self.page_content)}, score={self.score!r}, page={self.page!r}, chunk_index={self.chunk_index!r})"
        )

    # --- Unified normalizer: props/metadata -> Document ---
    @classmethod
    def from_props(
        cls,
        props: dict,
        md: Optional[dict] = None,
        *,
        text_key: str = "content",
        page_content: Optional[str] = None,
        weaviate_id: Optional[str] = None,
    ):
        """
        Normalize heterogeneous payloads (Weaviate props, LangChain metadata) into a Document.
        - `props`: primary key/value source (can be Weaviate .properties or LC metadata)
        - `md`: secondary source for scores/ids (can equal props)
        - `text_key`: primary text field key when coming from Weaviate (e.g., "text")
        - `page_content`: explicit content override (LC Document.page_content)
        - `weaviate_id`: explicit id override (for Weaviate objects)
        """
        props = props or {}
        md = md or {}

        # content resolution priority: explicit override > text_key > "content" > "text"
        content_val = (
            page_content
            if page_content is not None
            else _pick(props, text_key, "content", "text", default="")
        )

        title = _pick(props, "title", "filename", default="")
        filename = _pick(props, "filename", default="")
        extension = _pick(props, "extension", default="")
        file_size = _as_int(_pick(props, "file_size", "fileSize", default=0), default=0)

        file_id = _pick(props, "file_id", "fileId")
        user_id = _pick(props, "user_id", "userId")
        chunk_id = _pick(props, "chunk_id", "chunkId")
        chunk_index = _as_int(_pick(props, "chunk_index", "chunkIndex"))
        page = _as_int(_pick(props, "page"))
        uri = _pick(props, "uri")
        labels = _pick(props, "labels", default=[]) or []
        source = _pick(props, "source", default="")

        # carry over score/dist/explain from md
        score = md.get("score") or md.get("__score")
        distance = md.get("distance")
        explain_score = md.get("explain_score") or md.get("explainScore")
        score_contrast = md.get("__score_contrast") or md.get("scoreContrast")

        # id resolution: explicit > md/weaviate > props
        wid = (
            weaviate_id
            or md.get("weaviate_id")
            or md.get("id")
            or props.get("weaviate_id")
            or props.get("id")
        )
        wid = str(wid) if wid else None

        # meta: keep original props minus heavy text
        meta = {k: v for k, v in props.items() if k not in {text_key, "content", "text"}}
        if wid:
            meta["weaviate_id"] = wid

        return cls(
            doc_id=wid,
            file_id=file_id,
            user_id=user_id,
            title=title,
            filename=filename,
            extension=extension,
            file_size=file_size if isinstance(file_size, int) else 0,
            labels=labels,
            source=source,
            uri=uri,
            chunk_id=str(chunk_id) if chunk_id is not None else None,
            chunk_index=_as_int(chunk_index),
            page=_as_int(page),
            page_content=content_val or "",
            snippet=None,
            score=score,
            distance=distance,
            explain_score=explain_score,
            score_contrast=score_contrast,
            meta=meta,
            metadata={**meta},
        )

    @staticmethod
    def to_json(document) -> dict:
        """Convert Document to camelCase JSON. Internal attrs stay snake_case; wire format is camelCase."""
        return {
            "id": document.doc_id,
            "fileId": document.file_id,
            "userId": document.user_id,
            "title": document.title,
            "filename": document.filename,
            "extension": document.extension,
            "fileSize": document.file_size,
            "labels": document.labels,
            "source": document.source,
            "uri": document.uri,
            "chunkId": document.chunk_id,
            "chunkIndex": document.chunk_index,
            "page": document.page,
            "content": document.page_content,
            "snippet": document.snippet,
            "score": document.score,
            "distance": document.distance,
            "explainScore": document.explain_score,
            "scoreContrast": document.score_contrast,
            "meta": document.meta,
            "metadata": document.metadata,
        }

    @staticmethod
    def from_json(doc_dict: dict, *_):
        """Reconstruct a Document from camelCase JSON (or compatible payload)."""
        # Normalize meta: may arrive as dict or JSON string
        raw_meta = doc_dict.get("meta", {}) or {}
        if isinstance(raw_meta, str):
            try:
                meta = json.loads(raw_meta)
            except json.JSONDecodeError:
                meta = {}
        else:
            meta = raw_meta

        return Document(
            doc_id=doc_dict.get("id") or doc_dict.get("weaviate_id"),
            file_id=doc_dict.get("fileId") or doc_dict.get("file_id"),
            user_id=doc_dict.get("userId") or doc_dict.get("user_id"),

            title=doc_dict.get("title", ""),
            filename=doc_dict.get("filename", "") or doc_dict.get("file_name", ""),
            extension=doc_dict.get("extension", ""),
            file_size=doc_dict.get("fileSize", doc_dict.get("file_size", 0)),
            labels=doc_dict.get("labels", []),
            source=doc_dict.get("source", ""),
            uri=doc_dict.get("uri"),

            chunk_id=str(doc_dict.get("chunkId") or doc_dict.get("chunk_id") or ""),
            chunk_index=doc_dict.get("chunkIndex", doc_dict.get("chunk_index")),
            page=doc_dict.get("page"),

            page_content=doc_dict.get("content", "") or doc_dict.get("text", ""),
            snippet=doc_dict.get("snippet"),

            score=doc_dict.get("score"),
            distance=doc_dict.get("distance"),
            explain_score=doc_dict.get("explainScore") or doc_dict.get("explain_score"),
            score_contrast=doc_dict.get("scoreContrast") or doc_dict.get("__score_contrast"),

            meta=meta,
            metadata=doc_dict.get("metadata", {}) or {},
        )

    @staticmethod
    def from_langchain(d):
        """Accept a LangChain-like Document (page_content + metadata) and normalize to our Document.
        Expected shape:
            - d.page_content: str
            - d.metadata: dict (may contain filename/file_id/chunk info/score/etc.)
        """
        md = getattr(d, "metadata", {}) or {}
        page_content = getattr(d, "page_content", "") or ""

        # Title/filename hints live in metadata; pass md as props as well
        return Document.from_props(
            props=md,
            md=md,
            text_key="content",          # LC doesn't use our "text" field; content is from page_content
            page_content=page_content,
            weaviate_id=md.get("weaviate_id") or md.get("id"),
        )

    @staticmethod
    def from_any(d, text_key: str = "content"):
        """Normalize various doc-like objects into our Document.
        Supports:
          - our Document (pass-through)
          - LangChain Document (has .page_content & .metadata)
          - dict payloads compatible with `from_json`
          - Weaviate SDK objects (have .properties / .metadata)
        """
        # 1) Already our Document
        if isinstance(d, Document):
            return d
        # 2) LangChain Document (duck-typing)
        if hasattr(d, "page_content") and hasattr(d, "metadata"):
            return Document.from_langchain(d)
        # 3) dict-like (camelCase or snake_case)
        if isinstance(d, dict):
            return Document.from_json(d)
        # 4) Weaviate SDK object (properties/metadata)
        props = getattr(d, "properties", None)
        if props is not None:
            # Reuse items_to_docs logic by building a single-item list
            return items_to_docs([d], text_key=text_key)[0]
        # Unknown type → best-effort empty
        return Document(page_content=str(d))

def items_to_docs(items, text_key: str):
    """
    Convert Weaviate query results into canonical Document objects while preserving score/metadata.
    - Accepts either raw dicts (already shaped) or Weaviate objects with .properties / .metadata.
    - `text_key` is the property name that holds full text content in Weaviate (e.g., "text").
    """
    docs = []
    for it in (items or []):
        # Normalize any incoming doc-like object (our Doc, LangChain Doc, dict, Weaviate object)
        if isinstance(it, Document) or isinstance(it, dict) or hasattr(it, "page_content") or hasattr(it, "properties"):
            try:
                doc = Document.from_any(it, text_key=text_key)
                docs.append(doc)
                continue
            except Exception:
                # fall through to legacy parsing below if normalization fails
                pass

        # Legacy Weaviate path (kept for resilience)
        props = getattr(it, "properties", None) or {}
        md_obj = getattr(it, "metadata", None)

        # Convert Weaviate metadata object (which may expose attributes) to dict safely
        md = {}
        if md_obj is not None:
            try:
                # Try attribute access first (weaviate SDK style)
                md = {
                    k: getattr(md_obj, k)
                    for k in ("score", "distance", "explain_score", "__score_contrast")
                    if hasattr(md_obj, k)
                }
            except Exception:
                md = {}
        # Carry uuid/id from object if present
        wid = getattr(it, "uuid", None) or getattr(it, "id", None)
        wid = str(wid) if wid else None

        doc = Document.from_props(
            props=props,
            md=md,
            text_key=text_key,
            page_content=None,
            weaviate_id=wid,
        )
        docs.append(doc)
    return docs
