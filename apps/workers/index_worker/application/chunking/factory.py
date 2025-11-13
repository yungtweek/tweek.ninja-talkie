from typing import Mapping, Type, Literal, cast, Final

from index_worker.application.chunking.MarkdownChunker import MarkdownChunker
# from index_worker.application.chunking.word import WordChunker
# from index_worker.application.chunking.char import CharChunker
# from index_worker.application.chunking.token import TokenChunker
from index_worker.application.chunking.base import BaseChunker, ChunkerMode


# supported chunkers
_CHUNKER_BY_KEY: Final[Mapping[str, type[BaseChunker]]] = cast(
    dict[str, type[BaseChunker]],
    cast(object, {
        "markdown": MarkdownChunker,
    })
)

def _guess_mode_from_extension(ext: str | None) -> ChunkerMode:
    """Infer chunker mode from file extension."""
    if not ext:
        return "token"

    lower = ext.lower()

    if lower.endswith(".md") or lower.endswith(".markdown"):
        return "markdown"

    if lower.endswith(".txt"):
        return "word"

    return "token"


def build_chunker(
    *,
    extension: str | None = None,
    mode: ChunkerMode | None = None,
    default: ChunkerMode = "token",
) -> BaseChunker:
    """Return a chunker implementation based on mode/extension.

    Resolution priority:
      1. explicit `mode`
      2. inferred from extension
      3. fallback `default`
    """

    # direct override
    if mode is None:
        mode = _guess_mode_from_extension(extension)

    # fallback
    mode = mode or default

    cls = _CHUNKER_BY_KEY.get(mode)

    if cls is None:
        raise ValueError(f"Unsupported chunker mode: {mode}")

    return cls()