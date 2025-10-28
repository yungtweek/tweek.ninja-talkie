import { Inject, Injectable, Logger } from '@nestjs/common';
import { Pool } from 'pg';
import { PG_POOL } from '@/modules/infra/database/database.module';

/** Shape of a row in file_metadata (subset for app use). */
export type FileMetadataRow = {
  id: string;
  bucket: string;
  key: string;
  filename: string;
  content_type: string | null;
  size: number | null;
  etag: string | null;
  owner_id: string;
  department_id: string | null;
  visibility: 'private' | 'department' | 'public' | 'followers';
  status: string;
  uploaded_at: string | null;
  modified_at: string | null;
  created_at: string;
  updated_at: string;
  language: string | null;
  chunk_count: number | null;
  embedding_model: string | null;
  indexed_at: string | null;
  vectorized_at: string | null;
  source_url: string | null;
  checksum: string | null;
  meta: any;
};

/** Slim row for list views (do not expose S3 key to clients). */
export type FileListItem = {
  id: string;
  filename: string;
  content_type: string | null;
  status: string;
  size: number | null;
  uploaded_at: string | null;
  created_at: string;
  visibility: 'private' | 'department' | 'public' | 'followers';
};

export type UpsertByKeyInput = {
  // Required identity
  bucket: string;
  key: string; // UNIQUE
  filename: string;
  ownerId: string;

  // Optional file props
  contentType?: string | null;
  size?: number | null;
  etag?: string | null;

  // Optional ownership / visibility
  departmentId?: string | null;
  visibility?: 'private' | 'department' | 'public' | 'followers';

  // Optional status + indexing meta
  status?: string; // pending | processing | done | failed | indexed | vectorized | deleted | ready
  uploadedAt?: string | null;
  modifiedAt?: string | null;
  language?: string | null;
  chunkCount?: number | null;
  embeddingModel?: string | null;
  indexedAt?: string | null;
  vectorizedAt?: string | null;
  sourceUrl?: string | null;
  checksum?: string | null;
  meta?: Record<string, any> | null;
};

export type UpdateIndexStatusInput = {
  file_id: string;
  chunk_count?: number | null;
  embedding_model?: string | null;
  indexed_at?: string | null;
  vectorized_at?: string | null;
  meta?: Record<string, any> | null; // merged as jsonb ||
  status?: string; // optional status override
};

export type UpdateIndexStatusByKeyInput = {
  bucket: string;
  key: string;
  size?: number | null;
  etag?: string | null;
  chunkCount?: number | null;
  embeddingModel?: string | null;
  indexedAt?: string | null;
  vectorizedAt?: string | null;
  meta?: Record<string, any> | null; // merged as jsonb ||
  status?: string; // optional status override
};
const logger = new Logger('IngestRepository');

@Injectable()
export class IngestRepository {
  constructor(@Inject(PG_POOL) private readonly pool: Pool) {}

  /**
   * List files visible to requester without exposing S3 key.
   * - Orders by uploaded_at DESC NULLS LAST, then created_at DESC, then id DESC.
   * - Supports keyset pagination via a cursor composed of (uploaded_at, created_at, id).
   * - Returns at most `first` items and a nextCursor (base64) if more remain.
   */
  async listRowsForUser(
    requesterId: string,
    first: number,
    after?: { uploadedAt: string | null; createdAt: string; id: string } | null,
  ): Promise<FileListItem[]> {
    const baseWhere = `(visibility = 'public' OR (visibility = 'private' AND owner_id = $1))`;
    const params: any[] = [requesterId];
    let sql: string;

    if (!after) {
      sql = `
        SELECT id, filename, content_type, status, size, uploaded_at, created_at, visibility
        FROM file_metadata
        WHERE ${baseWhere}
          AND status NOT IN ('deleted', 'deleting')
        ORDER BY uploaded_at DESC NULLS LAST, created_at DESC, id DESC
        LIMIT $2
      `;
      params.push(first + 1); // over-fetch
    } else {
      sql = `
        SELECT id, filename, content_type, status, size, uploaded_at, created_at, visibility
        FROM file_metadata
        WHERE ${baseWhere}
          AND status NOT IN ('deleted', 'deleting')
          AND (COALESCE(uploaded_at, to_timestamp(0)), created_at, id)
          < (COALESCE($2::timestamptz, to_timestamp(0)), $3::timestamptz, $4::uuid)
        ORDER BY uploaded_at DESC NULLS LAST, created_at DESC, id DESC
        LIMIT $5
      `;
      params.push(after.uploadedAt, after.createdAt, after.id, first + 1);
    }

    const { rows } = await this.pool.query<FileListItem>(sql, params);
    return rows;
  }

  /**
   * Insert or update a file_metadata row by its unique key.
   * Only provided fields are written; others remain unchanged on conflict.
   */
  async upsertByKey(input: UpsertByKeyInput): Promise<FileMetadataRow> {
    const baseRequired: Array<[string, unknown]> = [
      ['bucket', input.bucket],
      ['key', input.key],
      ['filename', input.filename],
      ['owner_id', input.ownerId],
    ];

    const optional: Array<[string, unknown]> = [];
    const pushOpt = (k: string, v: unknown) => {
      if (v !== undefined) optional.push([k, v]);
    };

    pushOpt('content_type', input.contentType ?? null);
    pushOpt('size', input.size ?? null);
    pushOpt('etag', input.etag ?? null);
    pushOpt('department_id', input.departmentId ?? null);
    pushOpt('visibility', input.visibility ?? 'private');
    pushOpt('status', input.status ?? 'pending');
    pushOpt('uploaded_at', input.uploadedAt ?? null);
    pushOpt('modified_at', input.modifiedAt ?? null);
    pushOpt('language', input.language ?? null);
    pushOpt('chunk_count', input.chunkCount ?? null);
    pushOpt('embedding_model', input.embeddingModel ?? null);
    pushOpt('indexed_at', input.indexedAt ?? null);
    pushOpt('vectorized_at', input.vectorizedAt ?? null);
    pushOpt('source_url', input.sourceUrl ?? null);
    pushOpt('checksum', input.checksum ?? null);
    pushOpt('meta', input.meta ?? {});

    const cols = [...baseRequired, ...optional].map(([k]) => k);
    const vals: unknown[] = [...baseRequired, ...optional].map(([, v]) => v);

    const insertCols = cols.map(c => `"${c}"`).join(', ');
    const insertParams = cols.map((_, i) => `$${i + 1}`).join(', ');

    // ON CONFLICT update set only provided optional fields + always bump updated_at
    const updateAssignments: string[] = optional.map(([k], i) => `"${k}" = EXCLUDED."${k}"`);
    updateAssignments.push('updated_at = now()');

    const sql = `
      INSERT INTO file_metadata (${insertCols})
      VALUES (${insertParams})
      ON CONFLICT (key)
      DO UPDATE SET ${updateAssignments.join(', ')}
      RETURNING *;
    `;

    try {
      const { rows } = await this.pool.query<FileMetadataRow>(sql, vals as any[]);
      return rows[0];
    } catch (e: any) {
      logger.error(`upsertByKey failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }

  /** Fetch by id */
  async getById(id: string): Promise<FileMetadataRow | null> {
    const sql = 'SELECT * FROM file_metadata WHERE id = $1 LIMIT 1';
    const { rows } = await this.pool.query<FileMetadataRow>(sql, [id]);
    return rows[0] ?? null;
  }

  /** Return the owner_id for a given file id, or null if not found. */
  async getOwnerId(fileId: string): Promise<string | null> {
    const sql = 'SELECT owner_id FROM file_metadata WHERE id = $1 LIMIT 1';
    const { rows } = await this.pool.query<{ owner_id: string }>(sql, [fileId]);
    return rows[0]?.owner_id ?? null;
  }

  /** Fetch by (bucket, key) */
  async getByKey(bucket: string, key: string): Promise<FileMetadataRow | null> {
    const sql = 'SELECT * FROM file_metadata WHERE bucket = $1 AND key = $2 LIMIT 1';
    const { rows } = await this.pool.query<FileMetadataRow>(sql, [bucket, key]);
    return rows[0] ?? null;
  }

  /** Partial update for index/vector fields (called by gateway on orchestration milestones). */
  async updateIndexStatus(input: UpdateIndexStatusInput): Promise<void> {
    const sets: string[] = [];
    const vals: any[] = [];
    let i = 1;

    const add = (col: string, val: any) => {
      sets.push(`"${col}" = $${i++}`);
      vals.push(val);
    };

    if (input.chunk_count !== undefined) add('chunk_count', input.chunk_count);
    if (input.embedding_model !== undefined) add('embedding_model', input.embedding_model);
    if (input.indexed_at !== undefined) add('indexed_at', input.indexed_at);
    if (input.vectorized_at !== undefined) add('vectorized_at', input.vectorized_at);
    if (input.status !== undefined) add('status', input.status);

    // meta merge: meta = coalesce(meta,'{}'::jsonb) || $x::jsonb
    if (input.meta !== undefined) {
      sets.push(`meta = coalesce(meta, '{}'::jsonb) || $${i}::jsonb`);
      vals.push(JSON.stringify(input.meta));
      i++;
    }

    sets.push('updated_at = now()');

    const sql = `UPDATE file_metadata SET ${sets.join(', ')} WHERE id = $${i}`;
    vals.push(input.file_id);

    try {
      await this.pool.query(sql, vals);
    } catch (e: any) {
      logger.error(`updateIndexStatus failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }

  /** Partial update by (bucket, key) for clients that don't know file_id. */
  async updateIndexStatusByKey(input: UpdateIndexStatusByKeyInput): Promise<string | null> {
    const sets: string[] = [];
    const vals: any[] = [];
    let i = 1;

    const add = (col: string, val: any) => {
      sets.push(`"${col}" = $${i++}`);
      vals.push(val);
    };

    if (input.chunkCount !== undefined) add('chunk_count', input.chunkCount);
    if (input.embeddingModel !== undefined) add('embedding_model', input.embeddingModel);
    if (input.indexedAt !== undefined) add('indexed_at', input.indexedAt);
    if (input.vectorizedAt !== undefined) add('vectorized_at', input.vectorizedAt);
    if (input.status !== undefined) add('status', input.status);

    // also allow updating object properties gathered at completePost
    if (input.size !== undefined) add('size', input.size);
    if (input.etag !== undefined) add('etag', input.etag);

    if (input.meta !== undefined) {
      sets.push(`meta = coalesce(meta, '{}'::jsonb) || $${i}::jsonb`);
      vals.push(JSON.stringify(input.meta));
      i++;
    }

    // always bump updated_at
    sets.push('updated_at = now()');

    // if nothing else to update (only updated_at), skip
    if (sets.length === 1) {
      return null;
    }

    // WHERE bucket ... AND key ...
    const sql = `UPDATE file_metadata SET ${sets.join(', ')} WHERE bucket = $${i} AND key = $${i + 1} RETURNING updated_at`;
    vals.push(input.bucket, input.key);

    try {
      const { rows } = await this.pool.query<{ updated_at: string }>(sql, vals);
      return rows[0]?.updated_at ?? null;
    } catch (e: any) {
      logger.error(`updateIndexStatusByKey failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }

  /** Mark file as failed and store reason into meta.reason */
  async markFailed(file_id: string, reason: string): Promise<void> {
    const sql = `
      UPDATE file_metadata
         SET status = 'failed',
             meta = jsonb_set(coalesce(meta, '{}'::jsonb), '{reason}', to_jsonb($2::text), true),
             updated_at = now()
       WHERE id = $1;
    `;
    try {
      await this.pool.query(sql, [file_id, reason]);
    } catch (e: any) {
      logger.error(`markFailed failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }

  /** Transition file status to 'deleting' (pre-delete state). */
  async markDeleting(file_id: string): Promise<void> {
    const sql = `
      UPDATE file_metadata
         SET status = 'deleting',
             updated_at = now(),
             delete_requested_at = now()
       WHERE id = $1;
    `;
    try {
      await this.pool.query(sql, [file_id]);
    } catch (e: any) {
      logger.error(`markDeleting failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }

  /** Mark failed by (bucket, key) for clients that don't know file_id */
  async markFailedByKey(bucket: string, key: string, reason: string): Promise<void> {
    const sql = `
      UPDATE file_metadata
         SET status = 'failed',
             meta = jsonb_set(coalesce(meta, '{}'::jsonb), '{reason}', to_jsonb($3::text), true),
             updated_at = now()
       WHERE bucket = $1 AND key = $2;
    `;
    try {
      await this.pool.query(sql, [bucket, key, reason]);
    } catch (e: any) {
      logger.error(`markFailedByKey failed: ${e?.message}`, e?.stack);
      throw e;
    }
  }
}
