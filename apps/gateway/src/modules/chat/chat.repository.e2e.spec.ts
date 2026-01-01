import dotenv from 'dotenv';
import crypto from 'crypto';
import { Pool } from 'pg';
import { Kysely, PostgresDialect } from 'kysely';
import { ChatRepository } from './chat.repository';
import type { DB } from '@/modules/infra/database/kysely/kysely.module';

dotenv.config({ path: '.env.local' });

jest.setTimeout(30000);

describe('ChatRepository (e2e, toolCallsJson aggregation)', () => {
  let pool: Pool;
  let db: Kysely<DB>;
  let repo: ChatRepository;

  beforeAll(() => {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error('DATABASE_URL must be set for chat repository e2e tests');
    }

    pool = new Pool({ connectionString });
    db = new Kysely<DB>({
      dialect: new PostgresDialect({ pool }),
    });
    repo = new ChatRepository(db);
  });

  afterAll(async () => {
    if (pool) {
      await db.destroy();
    }
  });

  it('aggregates tool call events into toolCallsJson', async () => {
    const userId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    const jobId = crypto.randomUUID();
    const publicNs = userId.replace(/-/g, '');

    try {
      await pool.query(
        `
        INSERT INTO users (id, username, email, pwd_shadow, public_ns, created_at, updated_at)
        VALUES ($1, $2, $3, NULL, $4, now(), now())
        ON CONFLICT (id) DO NOTHING
        `,
        [userId, `test-user-${userId.slice(0, 8)}`, null, publicNs],
      );

      await pool.query(
        `
        INSERT INTO chat_sessions (id, user_id, title, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'active', now(), now())
        `,
        [sessionId, userId, 'tool call test'],
      );

      await pool.query(
        `
        INSERT INTO chat_messages (id, session_id, turn, role, mode, message_index, content, job_id, status)
        VALUES ($1, $2, 1, 'assistant', 'gen', 1, 'hello', $3, 'done')
        `,
        [crypto.randomUUID(), sessionId, jobId],
      );

      const inProgressPayload = {
        tool: 'health_check',
        callId: 'call-1',
        attempt: 1,
        argsPreview: '{"foo":"bar"}',
      };
      const completedPayload = {
        tool: 'health_check',
        callId: 'call-1',
        attempt: 1,
        tookMs: 25,
        argsPreview: '{"foo":"bar"}',
        resultPreview: '{"ok":true}',
      };

      await pool.query(
        `
        INSERT INTO job_events (job_id, user_id, session_id, event, payload)
        VALUES ($1, $2, $3, $4, $5::jsonb),
               ($1, $2, $3, $6, $7::jsonb)
        `,
        [
          jobId,
          userId,
          sessionId,
          'tool.call.in_progress',
          JSON.stringify(inProgressPayload),
          'tool.call.completed',
          JSON.stringify(completedPayload),
        ],
      );

      const messageRow = await pool.query(
        `SELECT job_id FROM chat_messages WHERE session_id = $1`,
        [sessionId],
      );
      expect(messageRow.rows[0]?.job_id).toBe(jobId);

      const eventsRow = await pool.query(
        `SELECT COUNT(*)::int AS count FROM job_events WHERE job_id = $1`,
        [jobId],
      );
      expect(eventsRow.rows[0]?.count).toBe(2);

      const rows = await repo.listMessagesBySession(sessionId, { first: 10 });
      expect(rows).toHaveLength(1);
      expect(rows[0].toolCallsJson).toBeTruthy();
      const toolCalls = rows[0].toolCallsJson as {
        order?: string[];
        calls?: Record<string, { tool?: string; attempt?: number; inProgress?: unknown; completed?: unknown }>;
      };
      expect(toolCalls.order?.length).toBe(1);
      const callId = toolCalls.order?.[0] ?? '';
      expect(callId).toBeTruthy();
      const entry = toolCalls.calls?.[callId];
      expect(entry).toBeTruthy();
      expect(entry).toMatchObject({ tool: 'health_check', attempt: 1 });
      expect(entry?.inProgress).toMatchObject(inProgressPayload);
      expect(entry?.completed).toMatchObject(completedPayload);
    } finally {
      try {
        await pool.query('DELETE FROM job_events WHERE job_id = $1', [jobId]);
        await pool.query('DELETE FROM chat_messages WHERE session_id = $1', [sessionId]);
        await pool.query('DELETE FROM chat_sessions WHERE id = $1', [sessionId]);
        await pool.query('DELETE FROM users WHERE id = $1', [userId]);
      } catch {
        // Best-effort cleanup; failures should not mask test assertions.
      }
    }
  });
});
