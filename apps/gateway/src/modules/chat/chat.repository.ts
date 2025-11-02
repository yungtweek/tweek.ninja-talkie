/**
 * ChatRepository
 * - Low-level data access for chat sessions/messages and job/outbox tables.
 * - Uses raw SQL (pg Pool) for predictable performance and query transparency.
 * - Returns Zod-validated rows where appropriate to keep callers type-safe.
 */
// src/modules/users/users.repository.ts
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ChatMessageZod, ChatSessionZod } from '@talkie/types-zod';
import { Pool } from 'pg';
import { PG_POOL } from '@/modules/infra/database/database.module';

/** Data access layer for chat-related entities (sessions, messages, jobs, outbox). */
@Injectable()
export class ChatRepository {
  private readonly logger = new Logger(ChatRepository.name);
  constructor(@Inject(PG_POOL) private readonly pool: Pool) {}

  /**
   * Create a new chat session for a user.
   * @param userId owner of the session
   * @param title optional title shown in session list
   * @returns newly created session id (uuid)
   */
  async createSession(userId: string, title?: string) {
    // Insert and return generated session id
    const sql = `INSERT INTO chat_sessions (user_id, title)
               VALUES ($1, $2) RETURNING id`;
    const { rows } = await this.pool.query<{ id: string }>(sql, [userId, title ?? null]);
    if (rows.length === 0) {
      // Should never happen, but keep repository safe for callers
      throw new Error('createSession: INSERT returned no id');
    }
    return rows[0].id;
  }

  /** Quick ownership existence check for (sessionId, userId) pair. */
  async ensureOwned(sessionId: string, userId: string) {
    const { rows } = await this.pool.query(
      `SELECT 1 FROM chat_sessions WHERE id=$1 AND user_id=$2`,
      [sessionId, userId],
    );
    return rows.length > 0;
  }

  /**
   * Insert a user message and allocate (message_index, turn) within a session.
   * - Uses a short transaction and row lock on the parent session to avoid index races.
   * - Computes next_index and next_turn based on current maxima.
   * - Returns identifiers and counters for downstream use.
   */
  async createUserMessage(
    sessionId: string,
    content: string,
    mode: 'gen' | 'rag' = 'gen',
    traceId?: string,
  ) {
    // Begin short-lived transaction
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');

      // Serialize concurrent writers within the same session
      await client.query(`SELECT id FROM chat_sessions WHERE id=$1 FOR UPDATE`, [sessionId]);

      // Compute next counters safely under the lock
      const { rows: indexRows } = await client.query<{ next_index: number }>(
        `SELECT COALESCE(MAX(message_index), 0) + 1 AS next_index FROM chat_messages WHERE session_id=$1;`,
        [sessionId],
      );
      if (indexRows.length === 0 || typeof indexRows[0]?.next_index !== 'number') {
        return Promise.reject(new Error('createUserMessage: failed to compute next_index'));
      }
      const nextIndex: number = indexRows[0].next_index;

      // Compute next counters safely under the lock
      const { rows: turnRows } = await client.query<{ next_turn: number }>(
        `SELECT COALESCE(MAX(turn), 0) + 1 AS next_turn FROM chat_messages WHERE session_id=$1;`,
        [sessionId],
      );
      if (turnRows.length === 0 || typeof turnRows[0]?.next_turn !== 'number') {
        return Promise.reject(new Error('createUserMessage: failed to compute next_turn'));
      }
      const nextTurn: number = turnRows[0].next_turn;

      // Persist the new message and return counters
      const insertSql = `
        INSERT INTO chat_messages (session_id, role, mode, content, message_index, turn, trace_id)
        VALUES ($1, 'user', $2, $3, $4, $5, $6)
        RETURNING id, message_index, turn, mode
      `;
      const { rows: insertRows } = await client.query(insertSql, [
        sessionId,
        mode,
        content,
        nextIndex,
        nextTurn,
        traceId ?? null,
      ]);

      // Commit transaction
      await client.query('COMMIT');
      return insertRows[0] as {
        id: string;
        message_index: number;
        turn: number;
        mode: 'gen' | 'rag';
      };
    } catch (error) {
      // On failure, rollback to preserve consistency
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  /** Upsert a job record to queued state (idempotent for retries). */
  async upsertJobQueued(jobId: string, sessionId: string, type: 'CHAT' | 'INGEST') {
    const sql = `
      INSERT INTO jobs (id, session_id, type, status)
      VALUES ($1, $2, $3, 'queued')
      ON CONFLICT (id)
      DO UPDATE SET
        session_id = EXCLUDED.session_id,
        type = EXCLUDED.type,
        status = 'queued',
        error = NULL,
        updated_at = now();
    `;
    await this.pool.query(sql, [jobId, sessionId, type]);
  }

  /**
   * Insert an event into the outbox table (for async dispatch).
   * @returns numeric outbox id for traceability
   */
  async insertOutbox(topic: string, key: string | null, payload: unknown) {
    const sql = `
      INSERT INTO outbox (topic, key, payload_json)
      VALUES ($1, $2, $3::jsonb)
      RETURNING id
    `;
    const { rows } = await this.pool.query(sql, [
      topic,
      key ?? null,
      JSON.stringify(payload ?? {}),
    ]);
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    return rows[0].id as number;
  }

  /**
   * Paginated messages for a session.
   * - Caller must ensure ownership before calling this method.
   * - Supports `before` (message_index) keyset pagination.
   * - Returns rows in ascending order (oldest→newest) for UI convenience.
   */
  async listMessagesBySession(
    sessionId: string,
    opts: { first: number; before?: number },
  ): Promise<ChatMessageZod[]> {
    // Clamp page size to [1, 100]
    const limit = Math.min(Math.max(opts.first ?? 20, 1), 100);
    const params: (string | number)[] = [sessionId];
    let idx = 3;
    // Ownership is validated by the caller (chatSession resolver). No user_id join here to keep this hot path fast.
    let sql = `
      SELECT cm.id,
             cm.role,
             cm.content,
             cm.turn,
             cm.message_index as "messageIndex",
             cm.sources_json as "sourcesJson"
      FROM chat_messages cm
      JOIN chat_sessions cs ON cs.id = cm.session_id
      WHERE cm.session_id = $1
    `;

    // Apply cursor (exclusive) if provided
    if (typeof opts.before === 'number') {
      sql += ` AND cm.message_index < $${idx++} `;
      params.push(opts.before);
    }
    sql += ` ORDER BY cm.message_index DESC LIMIT ${limit};`;
    // Fetch in DESC for efficient index usage
    const { rows } = await this.pool.query<ChatMessageZod>(sql, params);
    // Return in ASC (front-ends render better this way)
    return rows.reverse();
  }
  // User-scoped session listing with keyset pagination
  /**
   * 사용자별 채팅 세션 목록 (키셋 페이지네이션)
   * - 정렬 키: COALESCE(last_message_at, created_at) DESC, id DESC
   * - after 커서: base64("<iso>|<uuid>")
   */
  async listSessionsByUser(
    userId: string,
    opts: { first?: number; after?: string },
  ): Promise<ChatSessionZod[]> {
    // Decode after-cursor: base64("<iso>|<uuid>")
    let afterTs: Date | undefined;
    let afterId: string | undefined;
    const limit = Math.min(Math.max(opts.first ?? 20, 1), 100);

    if (opts.after) {
      try {
        const decoded = Buffer.from(opts.after, 'base64').toString('utf8');
        const [iso, id] = decoded.split('|');
        const ts = new Date(iso);
        if (!Number.isNaN(ts.getTime()) && id && id.length > 0) {
          afterTs = ts;
          afterId = id;
        }
      } catch {
        // ignore invalid cursor
      }
    }

    // Base query params start with the current user id
    const params: (string | Date)[] = [userId];
    let idx = 2;
    // Include latest message info via LATERAL subquery (for preview/timestamp)
    const sql = [
      `SELECT cs.id as id,
              cs.title as title,
              cs.created_at as "createdAt",
              cs.updated_at as "updatedAt",
              lm.last_message_at as "lastMessageAt",
              lm.last_message_preview as "lastMessagePreview"
       FROM chat_sessions cs
       LEFT JOIN LATERAL (
         SELECT cm.created_at    AS last_message_at,
                LEFT(cm.content, 120) AS last_message_preview
         FROM chat_messages cm
         WHERE cm.session_id = cs.id
         ORDER BY cm.message_index DESC
         LIMIT 1
       ) lm ON TRUE
       WHERE cs.user_id = $1
       AND cs.status NOT IN ('deleting', 'deleted')`,
      afterTs && afterId
        ? ` AND (COALESCE(lm.last_message_at, cs.created_at), cs.id) < ($${idx++}, $${idx++})`
        : '',
      // Order by latest activity then id to ensure deterministic pagination
      ` ORDER BY COALESCE(lm.last_message_at, cs.created_at) DESC, cs.id DESC
        LIMIT ${limit};`,
    ].join('');

    // Append decoded cursor params when present
    if (afterTs && afterId) {
      params.push(afterTs, afterId);
    }

    // Return raw rows; caller (resolver) may further map/shape
    const { rows } = await this.pool.query<ChatSessionZod>(sql, params);

    return rows;
  }

  /** Resolve session owner (user_id) or null if not found. */
  async getUserId(sessionId: string): Promise<string | null> {
    const sql = 'SELECT user_id FROM chat_sessions WHERE id = $1 LIMIT 1';
    const { rows } = await this.pool.query<{ user_id: string }>(sql, [sessionId]);
    return rows[0]?.user_id ?? null;
  }

  /** Get full session meta for validation and GraphQL hydration. */
  async getSessionMeta(sessionId: string): Promise<{
    userId: string;
    title: string | null;
    createdAt: Date;
    updatedAt: Date;
  } | null> {
    const sql = `
    SELECT user_id AS "userId",
           title,
           created_at AS "createdAt",
           updated_at AS "updatedAt"
      FROM chat_sessions
     WHERE id = $1
     LIMIT 1
  `;
    const { rows } = await this.pool.query<{
      userId: string;
      title: string | null;
      createdAt: Date;
      updatedAt: Date;
    }>(sql, [sessionId]);

    if (rows.length === 0) return null;
    const r = rows[0];
    // Normalize to the exact return shape and avoid `any` escapes
    return {
      userId: r.userId,
      title: r.title,
      createdAt: r.createdAt,
      updatedAt: r.updatedAt,
    };
  }

  /** Mark session as logically deleting; background worker will finalize. */
  async markSessionDeleting(sessionId: string): Promise<void> {
    const sql = `
      UPDATE chat_sessions
         SET status = 'deleting',
             updated_at = now(),
             delete_requested_at = now()
       WHERE id = $1;
    `;
    try {
      // Best-effort update; errors are logged and rethrown for upstream handling
      await this.pool.query(sql, [sessionId]);
    } catch (e: unknown) {
      if (e instanceof Error) {
        this.logger.error(`markSessionDeleting failed: ${e.message}`, e.stack);
      } else {
        this.logger.error(`markSessionDeleting failed: ${String(e)}`);
      }
      throw e;
    }
  }
}
