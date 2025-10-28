# apps/workers/index_worker/application/cleanup_file.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from index_worker.domain.ports import VectorRepository, MetadataRepo

@dataclass
class CleanupResult:
    file_id: str
    deleted_count: int
    reason: str

async def cleanup_file(
        user_id: str,
        file_id: str,
        reason: str,
        vector_repo: 'VectorRepository',
        metadata_repo: 'MetadataRepo',
        job_id: str,
        logger,
) -> CleanupResult:
    """
    Remove vectors for the given file and mark metadata as deleted.
    Idempotent: multiple runs are safe (delete count may be 0).
    """
    deleted = await vector_repo.delete_by_user_file(user_id=user_id, file_id=file_id)
    logger.info(f"[{job_id}] cleanup_file: file_id={file_id} deleted={deleted}")

    # Prefer the new API; fallback for older implementations
    try:
        await metadata_repo.mark_deleted(file_id, deleted_count=deleted, reason=reason)
    except AttributeError:
        await metadata_repo.update_index_status(
            file_id,
            status="deleted",
            meta={"deleted_count": deleted, "reason": reason},
        )

    return CleanupResult(file_id=file_id, deleted_count=deleted, reason=reason)