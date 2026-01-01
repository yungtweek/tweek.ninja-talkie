/**
 * ChatRepository
 * - Low-level data access for chat sessions/messages and job/outbox tables.
 * - Uses Kysely for typed queries; complex JSONB queries use typed raw SQL.
 * - Returns Zod-validated rows where appropriate to keep callers type-safe.
 */
// src/modules/users/users.repository.ts
import { Inject, Injectable, Logger } from '@nestjs/common';
import { ChatMessageZod, ChatSessionZod } from '@talkie/types-zod';
import { Kysely, sql } from 'kysely';
import { DB, KYSELY } from '@/modules/infra/database/kysely/kysely.module';

// SQL fragments for RAG event JSON composition in listMessagesBySession.
const jobEventPayload = (event: string) => sql`
  (
    SELECT je.payload
    FROM job_events je
    WHERE je.job_id = cm.job_id
      AND je.event = ${event}
    ORDER BY je.created_at DESC
    LIMIT 1
  )
`;

const ragEventPair = (prefix: string) => sql`
  NULLIF(
    jsonb_strip_nulls(
      jsonb_build_object(
        'inProgress', ${jobEventPayload(`${prefix}.in_progress`)},
        'completed', ${jobEventPayload(`${prefix}.completed`)}
      )
    ),
    '{}'::jsonb
  )
`;

const ragSearchWrapper = sql`
  NULLIF(
    jsonb_strip_nulls(
      jsonb_build_object(
        'searchCall', ${ragEventPair('rag_search_call')}
      )
    ),
    '{}'::jsonb
  )
`;

const ragStages = sql`
  NULLIF(
    jsonb_strip_nulls(
      jsonb_build_object(
        'retrieve', ${ragEventPair('rag_retrieve')},
        'rerank', ${ragEventPair('rag_rerank')},
        'mmr', ${ragEventPair('rag_mmr')},
        'compress', ${ragEventPair('rag_compress')}
      )
    ),
    '{}'::jsonb
  )
`;

const ragSearchJson = sql`
  NULLIF(
    jsonb_strip_nulls(
      jsonb_build_object(
        'wrapper', ${ragSearchWrapper},
        'stages', ${ragStages}
      )
    ),
    '{}'::jsonb
  )
`;

const toolCallsJson = sql`
  NULLIF(
    jsonb_strip_nulls(
      (
        WITH tool_calls AS (
          SELECT
            COALESCE(je.payload->>'callId', je.payload->>'tool') AS call_id,
            MAX(je.payload->>'tool') AS tool_name,
            MAX((je.payload->>'attempt')::int) AS attempt_num,
            MIN(je.created_at) AS first_seen
          FROM job_events je
          WHERE je.job_id = cm.job_id
            AND je.event IN ('tool.call.in_progress', 'tool.call.completed')
            AND COALESCE(je.payload->>'callId', je.payload->>'tool') IS NOT NULL
          GROUP BY 1
        )
        SELECT jsonb_build_object(
          'order', (SELECT jsonb_agg(call_id ORDER BY first_seen) FROM tool_calls),
          'calls', (
            SELECT jsonb_object_agg(
              tc.call_id,
              jsonb_strip_nulls(
                jsonb_build_object(
                  'tool', tc.tool_name,
                  'attempt', tc.attempt_num,
                  'inProgress', tip.payload,
                  'completed', tco.payload
                )
              )
            )
            FROM tool_calls tc
            LEFT JOIN LATERAL (
              SELECT je2.payload
              FROM job_events je2
              WHERE je2.job_id = cm.job_id
                AND je2.event = 'tool.call.in_progress'
                AND COALESCE(je2.payload->>'callId', je2.payload->>'tool') = tc.call_id
              ORDER BY je2.created_at DESC
              LIMIT 1
            ) tip ON true
            LEFT JOIN LATERAL (
              SELECT je3.payload
              FROM job_events je3
              WHERE je3.job_id = cm.job_id
                AND je3.event = 'tool.call.completed'
                AND COALESCE(je3.payload->>'callId', je3.payload->>'tool') = tc.call_id
              ORDER BY je3.created_at DESC
              LIMIT 1
            ) tco ON true
          )
        )
      )
    ),
    '{}'::jsonb
  )
`;

/** Data access layer for chat-related entities (sessions, messages, jobs, outbox). */
@Injectable()
export class ChatRepository {
  private readonly logger = new Logger(ChatRepository.name);
  constructor(@Inject(KYSELY) private readonly db: Kysely<DB>) {}

  /**
   * Create a new chat session for a user.
   * @param userId owner of the session
   * @param title optional title shown in session list
   * @returns newly created session id (uuid)
   */
  async createSession(userId: string, title?: string) {
    const row = await this.db
      .insertInto('chat_sessions')
      .values({
        user_id: userId,
        title: title ?? null,
      })
      .returning('id')
      .executeTakeFirst();
    if (!row?.id) {
      // Should never happen, but keep repository safe for callers
      throw new Error('createSession: INSERT returned no id');
    }
    return row.id;
  }

  /** Quick ownership existence check for (sessionId, userId) pair. */
  async ensureOwned(sessionId: string, userId: string) {
    const row = await this.db
      .selectFrom('chat_sessions')
      .select('id')
      .where('id', '=', sessionId)
      .where('user_id', '=', userId)
      .executeTakeFirst();
    return !!row;
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
    return this.db.transaction().execute(async trx => {
      // Serialize concurrent writers within the same session
      await trx
        .selectFrom('chat_sessions')
        .select('id')
        .where('id', '=', sessionId)
        .forUpdate()
        .executeTakeFirst();

      const indexRow = await trx
        .selectFrom('chat_messages')
        .select(sql<number>`COALESCE(MAX(message_index), 0) + 1`.as('next_index'))
        .where('session_id', '=', sessionId)
        .executeTakeFirst();
      if (!indexRow || typeof indexRow.next_index !== 'number') {
        throw new Error('createUserMessage: failed to compute next_index');
      }
      const nextIndex = indexRow.next_index;

      const turnRow = await trx
        .selectFrom('chat_messages')
        .select(sql<number>`COALESCE(MAX(turn), 0) + 1`.as('next_turn'))
        .where('session_id', '=', sessionId)
        .executeTakeFirst();
      if (!turnRow || typeof turnRow.next_turn !== 'number') {
        throw new Error('createUserMessage: failed to compute next_turn');
      }
      const nextTurn = turnRow.next_turn;

      const inserted = await trx
        .insertInto('chat_messages')
        .values({
          session_id: sessionId,
          role: 'user',
          mode,
          content,
          message_index: nextIndex,
          turn: nextTurn,
          trace_id: traceId ?? null,
        })
        .returning(['id', 'message_index', 'turn', 'mode'])
        .executeTakeFirst();

      if (!inserted) {
        throw new Error('createUserMessage: INSERT returned no id');
      }

      return {
        id: inserted.id,
        message_index: inserted.message_index,
        turn: inserted.turn,
        mode: inserted.mode as 'gen' | 'rag',
      };
    });
  }

  /** Upsert a job record to queued state (idempotent for retries). */
  async upsertJobQueued(jobId: string, sessionId: string, type: 'CHAT' | 'INGEST') {
    await this.db
      .insertInto('jobs')
      .values({
        id: jobId,
        session_id: sessionId,
        type,
        status: 'queued',
      })
      .onConflict(oc =>
        oc.column('id').doUpdateSet({
          session_id: sessionId,
          type,
          status: 'queued',
          error: null,
          updated_at: sql`now()`,
        }),
      )
      .execute();
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
    const conditions = [sql`cm.session_id = ${sessionId}`];

    // Apply cursor (exclusive) if provided
    if (typeof opts.before === 'number') {
      conditions.push(sql`cm.message_index < ${opts.before}`);
    }

    const result = await sql<ChatMessageZod>`
      SELECT cm.id,
             cm.role,
             cm.content,
             cm.turn,
             cm.message_index as "messageIndex",
             cm.sources_json as "sourcesJson",
             (
               SELECT jsonb_agg(
                 jsonb_build_object(
                   'sourceId', mc.source_id,
                   'fileName', mc.file_name,
                   'fileUri', mc.file_uri,
                   'chunkId', mc.chunk_id,
                   'page', mc.page,
                   'snippet', mc.snippet,
                   'rerankScore', mc.rerank_score
                 )
                 ORDER BY mc.source_id
             )
               FROM message_citations mc
               WHERE mc.message_id = cm.id
            ) as "citationsJson"
            ,
            ${ragSearchJson} as "ragSearchJson",
            ${toolCallsJson} as "toolCallsJson"
      FROM chat_messages cm
      JOIN chat_sessions cs ON cs.id = cm.session_id
      WHERE ${sql.join(conditions, sql` AND `)}
      ORDER BY cm.message_index DESC
      LIMIT ${limit}
    `.execute(this.db);
    // Fetch in DESC for efficient index usage
    // Return in ASC (front-ends render better this way)
    return result.rows.reverse();
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

    const afterFilter =
      afterTs && afterId
        ? sql`AND (COALESCE(lm.last_message_at, cs.created_at), cs.id) < (${afterTs}, ${afterId})`
        : sql``;

    const result = await sql<ChatSessionZod>`
      SELECT cs.id as id,
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
      WHERE cs.user_id = ${userId}
        AND cs.status NOT IN ('deleting', 'deleted')
        ${afterFilter}
      ORDER BY COALESCE(lm.last_message_at, cs.created_at) DESC, cs.id DESC
      LIMIT ${limit}
    `.execute(this.db);

    return result.rows;
  }

  /** Resolve session owner (user_id) or null if not found. */
  async getUserId(sessionId: string): Promise<string | null> {
    const row = await this.db
      .selectFrom('chat_sessions')
      .select('user_id')
      .where('id', '=', sessionId)
      .executeTakeFirst();
    return row?.user_id ?? null;
  }

  /** Get full session meta for validation and GraphQL hydration. */
  async getSessionMeta(sessionId: string): Promise<{
    userId: string;
    title: string | null;
    createdAt: Date;
    updatedAt: Date;
  } | null> {
    const row = await this.db
      .selectFrom('chat_sessions')
      .select([
        sql<string>`user_id`.as('userId'),
        'title',
        sql<Date>`created_at`.as('createdAt'),
        sql<Date>`updated_at`.as('updatedAt'),
      ])
      .where('id', '=', sessionId)
      .executeTakeFirst();

    if (!row) return null;
    // Normalize to the exact return shape and avoid `any` escapes
    return {
      userId: row.userId,
      title: row.title,
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    };
  }

  /** Mark session as logically deleting; background worker will finalize. */
  async markSessionDeleting(sessionId: string): Promise<void> {
    try {
      // Best-effort update; errors are logged and rethrown for upstream handling
      await this.db
        .updateTable('chat_sessions')
        .set({
          status: 'deleting',
          updated_at: sql`now()`,
          delete_requested_at: sql`now()`,
        })
        .where('id', '=', sessionId)
        .execute();
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
