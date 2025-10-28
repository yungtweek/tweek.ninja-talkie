import asyncpg
from datetime import datetime
from index_worker.domain.ports import MetadataRepo
import json
from typing import Optional


class PgMetadataRepo(MetadataRepo):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def update_index_status(self, file_id, **kwargs):
        """
        Update basic columns and optionally update JSONB meta using either:
        - meta_path (list[str]) + meta_value (Any): uses jsonb_set at the given path
        - meta (str JSON): shallow-merge into meta via (meta || $jsonb)
        """
        # Extract special JSON args
        meta_path = kwargs.pop("meta_path", None)  # expect list[str]
        meta_value = kwargs.pop("meta_value", None)  # any JSON-serializable
        meta_merge = kwargs.pop("meta", None)  # str (JSON) or dict (we will dumps)

        # normal scalar columns (status, embedding_model, indexed_at, vectorized_at, chunk_count ...)
        fields = {k: v for k, v in kwargs.items() if v is not None}

        set_clauses = []
        vals = []
        i = 2  # $1 is file_id

        for k, v in fields.items():
            set_clauses.append(f'"{k}" = ${i}')
            vals.append(v)
            i += 1

        # JSONB: jsonb_set at a specific path
        if meta_path is not None and meta_value is not None:
            set_clauses.append(
                f"meta = jsonb_set(coalesce(meta, '{{}}'::jsonb), ${i}::text[], ${i+1}::jsonb, true)"
            )
            vals.append(meta_path)
            vals.append(json.dumps(meta_value))
            i += 2
        # JSONB: shallow merge (meta || $jsonb)
        elif meta_merge is not None:
            if not isinstance(meta_merge, str):
                meta_merge = json.dumps(meta_merge)
            set_clauses.append(
                f"meta = coalesce(meta, '{{}}'::jsonb) || ${i}::jsonb"
            )
            vals.append(meta_merge)
            i += 1

        # always bump updated_at
        set_clauses.append("updated_at = now()")

        query = f"UPDATE file_metadata SET {', '.join(set_clauses)} WHERE id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, file_id, *vals)

    async def get_metadata(self, file_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM file_metadata WHERE id=$1", file_id)
            return dict(row) if row else None

    async def mark_failed(self, file_id, reason: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE file_metadata
                SET status='failed',
                    meta = jsonb_set(coalesce(meta, '{}'::jsonb), '{reason}', to_jsonb($2::text), true),
                    updated_at = now()
                WHERE id=$1
                """,
                file_id, reason
            )

    async def mark_deleted(self, file_id: str, deleted_count: Optional[int] = None, reason: Optional[str] = None):
        """
        Mark the file as deleted (status='deleted').
        Optionally persist the number of deleted vectors and a free-form reason.
        """
        set_clauses = ["status='deleted'", "updated_at = now()", "vectors_deleted_at = now()"]
        vals = []
        i = 2  # $1 is file_id

        # Build meta update expression only if we have fields to write
        meta_expr = "coalesce(meta, '{}'::jsonb)"
        touched_meta = False

        if reason is not None:
            meta_expr = f"jsonb_set({meta_expr}, '{{reason}}', to_jsonb(${i}::text), true)"
            vals.append(reason)
            i += 1
            touched_meta = True

        if deleted_count is not None:
            meta_expr = f"jsonb_set({meta_expr}, '{{deleted_count}}', to_jsonb(${i}::int), true)"
            vals.append(deleted_count)
            i += 1
            touched_meta = True

        if touched_meta:
            set_clauses.append(f"meta = {meta_expr}")

        query = f"""UPDATE file_metadata
                     SET {', '.join(set_clauses)}
                     WHERE id = $1"""
        async with self.pool.acquire() as conn:
            await conn.execute(query, file_id, *vals)