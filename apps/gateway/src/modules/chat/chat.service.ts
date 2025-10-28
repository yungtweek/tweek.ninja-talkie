/**
 * ChatService
 * - Coordinates chat session creation, message persistence, and job enqueueing.
 * - Produces Kafka events for downstream LLM workers and publishes Redis-based SSE streams.
 * - Also bridges Redis streams for chat and session-level events.
 */
// src/modules/chat/chat.service.ts
import { Inject, Injectable, Logger, MessageEvent } from '@nestjs/common';
import Redis from 'ioredis';
import { randomUUID } from 'node:crypto';
import { Observable } from 'rxjs';
import { KafkaService } from '../infra/kafka/kafka.service';
import { EnqueueInput } from './dto/enqueue.zod';
import { ChatRepository } from '@/modules/chat/chat.repository';
import { PubSubEngine } from 'graphql-subscriptions';
import { SESSION_PUBSUB } from '@/modules/infra/pubsub/pubsub.module';
import { z } from 'zod';
import type { AuthUser } from '@/modules/auth/current-user.decorator';
import { SessionEventType } from '@/modules/chat/gql/chat.session.resolver';

const StreamEventSchema = z
  .object({
    event: z.string().optional(),
    userId: z.string(),
    jobId: z.string(),
    sessionId: z.string().optional(),
    data: z.unknown().optional(),
    ts: z.number().optional(),
  })
  .loose();
type StreamEvent = z.infer<typeof StreamEventSchema>;

const sessionEventSchema = z
  .object({
    type: z.enum(SessionEventType).or(z.string()).optional(),
    userId: z.string(),
    session: z
      .object({
        id: z.string(),
        title: z.string().optional(),
      })
      .optional(),
    ts: z.number().optional(),
  })
  .loose();

/** Core service layer handling enqueueing, Kafka publishing, and Redis stream bridges. */
@Injectable()
export class ChatService {
  private redis: Redis;
  private readonly logger = new Logger(ChatService.name);
  constructor(
    private readonly kafka: KafkaService,
    private readonly chatRepo: ChatRepository,
    @Inject(SESSION_PUBSUB) private readonly pubSub: PubSubEngine,
  ) {
    this.redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379');
  }

  /**
   * Enqueue a chat request and create or reuse an existing session.
   * - Persists the user message and upserts a job in `jobs` table.
   * - Publishes Kafka event (`chat.request`) for worker consumption.
   * - On failure, falls back to outbox for reliable delivery.
   * - If the session is new, emits a title-generation job.
   */
  async enqueue(dto: EnqueueInput, user: AuthUser) {
    // Create or reuse chat session for the user
    const { sessionId, isNew } = await this._createOrUseSession(dto, user);

    const jobId = dto.jobId;
    const userId = user.sub;

    const payload = {
      jobId,
      userId,
      sessionId,
      message: dto.message,
      mode: dto.mode,
    };

    // Save user message and track as job
    await this.chatRepo.createUserMessage(sessionId, dto.message, dto.mode);
    await this.chatRepo.upsertJobQueued(jobId, sessionId, 'CHAT');

    // If a new session, trigger async title generation
    if (isNew) {
      const traceId = randomUUID();
      const titlePayload = {
        traceId,
        jobId,
        userId: userId,
        sessionId,
        message: dto.message,
      };
      // this.logger.debug('titlePayload', titlePayload);
      try {
        await this.kafka.produce('chat.title.generate', titlePayload, traceId);
      } catch {
        await this.chatRepo.insertOutbox('chat.title.generate', traceId, titlePayload);
      }
    }

    try {
      // Publish main chat request to Kafka worker
      await this.kafka.produce('chat.request', payload, jobId);
      // (선택) jobs.status='processing' 으로 업데이트 가능
    } catch {
      // On failure, push to outbox for later retry
      await this.chatRepo.insertOutbox('chat.request', jobId, payload);
      // (선택) jobs.status='queued' 유지
    }

    return { sessionId, jobId };
  }

  /**
   * Subscribe to Redis Stream for real-time chat output tokens.
   * - Uses `xread` blocking read loop to emit events as Server-Sent Events (SSE).
   * - Filters by jobId and userId to ensure isolation.
   * - Emits `ping` heartbeat every 15 seconds when idle.
   */
  chatStream(jobId: string, user: AuthUser, lastId = '0-0'): Observable<MessageEvent> {
    // Create a dedicated Redis connection for streaming
    const reader = this.redis.duplicate();
    const userId = user.sub;
    const streamKey = `sse:chat:${jobId}:${userId}:events`;
    return new Observable<MessageEvent>(subscriber => {
      let cursor = lastId;
      let stopped = false;

      // Handle Redis connection errors gracefully
      const onError = (err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        if (!stopped && !subscriber.closed) {
          subscriber.next({ type: 'error', data: { message } });
          stopped = true;
          subscriber.complete();
        }
      };
      reader.on('error', onError);

      const loop = async () => {
        // Continuous polling loop with graceful stop condition
        while (!stopped && !subscriber.closed) {
          try {
            // Block for up to 15 seconds waiting for new messages
            const resp = await reader.xread('BLOCK', 15000, 'STREAMS', streamKey, cursor);

            if (resp && resp.length > 0) {
              const [, entries] = resp[0];
              for (const [id, fields] of entries as [string, Array<string | Buffer>][]) {
                cursor = id;

                // Convert flat Redis field array to key-value object
                const obj: Record<string, string> = Object.fromEntries(
                  Array.from({ length: fields.length / 2 }, (_, i) => {
                    const k = String(fields[i * 2]);
                    const v = String(fields[i * 2 + 1] ?? '');
                    return [k, v];
                  }),
                );

                const raw = obj['data'];

                let evt: StreamEvent | null = null;
                try {
                  const parsed = raw
                    ? (JSON.parse(raw) as unknown)
                    : { event: 'message', data: null };
                  // Validate and coerce incoming event payload
                  evt = StreamEventSchema.parse(parsed);
                } catch {
                  // 잘못된 이벤트는 무시하거나 DLQ로 보낼 수 있음. 여기서는 무시.
                  continue;
                }

                // Security filter: only emit events belonging to this user/job
                if (evt.userId !== userId && evt.jobId !== jobId) continue;

                // 외부로는 userId 같은 내부 필드는 제거(마스킹)
                const { userId: _omit, ...publicEvt } = evt as Record<string, unknown>;
                const eventName = typeof evt.event === 'string' ? evt.event : 'message';

                // Emit as SSE event to client
                subscriber.next({ type: eventName, data: publicEvt });

                if (eventName === 'done' || eventName === 'error') {
                  stopped = true;
                  subscriber.complete();
                  break;
                }
              }
            } else {
              // Emit heartbeat ping if no new events received
              subscriber.next({ type: 'ping', data: { ts: Date.now() } });
            }
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            subscriber.next({ type: 'error', data: { message } });
            stopped = true;
            subscriber.complete();
          }
        }
      };

      // Fire and forget the loop
      void loop();

      // Cleanup listener and close connection when unsubscribed
      return () => {
        stopped = true;
        try {
          reader.removeListener('error', onError);
        } catch {
          this.logger.warn('Redis reader already disconnected');
        }
        try {
          reader.disconnect();
        } catch {
          this.logger.warn('Redis reader already disconnected');
        }
      };
    });
  }

  /**
   * Subscribe to session-level Redis Stream (CREATED/UPDATED/DELETED events).
   * - Emits events as SSE stream with filtering by user.
   * - Keeps connection alive with periodic heartbeats.
   */
  sessionEvents(
    jobId: string, // kept for signature compatibility, not used for keying
    user: AuthUser,
    lastId = '0-0',
  ): Observable<MessageEvent> {
    const userId = user.sub;
    // Redis key scoped to user's session event stream
    const streamKey = `sse:session:${jobId}:${userId}:events`;
    const reader = this.redis.duplicate();
    return new Observable<MessageEvent>(subscriber => {
      let cursor = lastId;
      let stopped = false;

      // Error handler for Redis connection
      const onError = (err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        if (!stopped && !subscriber.closed) {
          subscriber.next({ type: 'error', data: { message } });
          stopped = true;
          subscriber.complete();
        }
      };
      reader.on('error', onError);

      const loop = async () => {
        // Long-polling loop for new stream entries
        while (!stopped && !subscriber.closed) {
          try {
            const resp = await reader.xread('BLOCK', 15000, 'STREAMS', streamKey, cursor);

            if (resp && resp.length > 0) {
              const [, entries] = resp[0];
              for (const [id, fields] of entries as [string, Array<string | Buffer>][]) {
                cursor = id;

                // Convert flat Redis array to object
                const obj: Record<string, string> = Object.fromEntries(
                  Array.from({ length: fields.length / 2 }, (_, i) => {
                    const k = String(fields[i * 2]);
                    const v = String(fields[i * 2 + 1] ?? '');
                    return [k, v];
                  }),
                );

                const raw = obj['data'];
                this.logger.debug('sessionEvents obj:', obj);
                this.logger.debug('sessionEvents raw:', raw);
                let evt: z.infer<typeof sessionEventSchema> | null = null;
                try {
                  const parsed = raw
                    ? (JSON.parse(raw) as unknown)
                    : { type: 'UPDATED', session: undefined };
                  // Validate event payload
                  evt = sessionEventSchema.parse(parsed);
                } catch {
                  // skip malformed
                  continue;
                }

                // Filter out events not owned by the user
                if (!evt || evt.userId !== userId) continue;

                // Emit to SSE subscriber
                const { userId: _omit, ...publicEvt } = evt as Record<string, unknown>;
                const eventName =
                  typeof evt.type === 'string' && evt.type.length > 0 ? evt.type : 'UPDATED';

                subscriber.next({ type: eventName, data: publicEvt });

                // (선택) 종료 조건은 없음: 세션 알림 스트림은 장기 유지 가능
                // 필요 시 특정 타입에서 종료하려면 아래 사용
                // if (eventName === 'DELETED') { stopped = true; subscriber.complete(); break; }
              }
            } else {
              // Heartbeat
              subscriber.next({ type: 'ping', data: { ts: Date.now() } });
            }
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            subscriber.next({ type: 'error', data: { message } });
            stopped = true;
            subscriber.complete();
          }
        }
      };

      void loop();

      // On unsubscribe, remove listeners and disconnect
      return () => {
        stopped = true;
        try {
          reader.removeListener('error', onError);
        } catch {
          this.logger.warn('Redis reader already disconnected');
        }
        try {
          reader.disconnect();
        } catch {
          this.logger.warn('Redis reader already disconnected');
        }
      };
    });
  }

  /**
   * Create a new chat session if not provided in the request.
   * - Emits a `CREATED` event into the session Redis stream for subscribers.
   * - Returns `{ sessionId, isNew }` tuple.
   */
  private async _createOrUseSession(dto: EnqueueInput, user: AuthUser) {
    // Use existing session if provided by client
    if (dto.sessionId) {
      // 기존 세션
      return { sessionId: dto.sessionId, isNew: false };
    }
    const jobId = dto.jobId;
    const userId = user.sub;
    // Build Redis key for session event stream
    const streamKey = `sse:session:${jobId}:${userId}:events`;
    // 신규 세션
    const sessionId = await this.chatRepo.createSession(userId);

    // Emit CREATED event for the new session (trimmed to ~10k entries)
    try {
      await this.redis.xadd(
        streamKey,
        'MAXLEN',
        '~',
        10000, // 자동 트림(약 1만개 유지)
        '*', // 서버가 ID 할당
        'data',
        JSON.stringify({
          type: SessionEventType.CREATED,
          userId,
          session: { id: sessionId },
        }),
        'ts',
        Date.now(),
      );
      // this.logger.debug('sessionEvents xadd published');
    } catch (e) {
      this.logger.warn(`sessionEvents xadd failed: ${e instanceof Error ? e.message : String(e)}`);
    }

    // this.logger.debug('sessionEvents published:');
    return { sessionId, isNew: true };
  }
}
