/**
 * SessionEventsStreamBridge
 * - Bridges Redis Stream (XREADGROUP) events into GraphQL PubSub for subscriptions.
 * - Converts raw Redis stream entries into typed SessionEvent payloads (Zod-validated).
 * - Runs a resilient polling loop with consumer-group semantics and ack-once delivery.
 */
import { Inject, Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import IORedis from 'ioredis';
import { SESSION_PUBSUB } from '@/modules/infra/pubsub/pubsub.module';
import type { PubSubEngine } from 'graphql-subscriptions';
import { STREAM_SESSION_EVENTS, TRIGGER_SESSION_EVENTS } from '@/common/constants';
import { z } from 'zod';

// Redis XREADGROUP result typing helpers
type XReadEntry = [id: string, fields: Array<string | Buffer>];
type XReadStream = [stream: string, entries: XReadEntry[]];
type XReadGroupResult = XReadStream[];

// Zod schema for validating incoming session event payloads
const SessionEventSchema = z.object({
  type: z.enum(['CREATED', 'UPDATED', 'DELETED']),
  session: z.unknown().optional(),
  userId: z.string().optional(),
});
type SessionEvent = z.infer<typeof SessionEventSchema>;

/**
 * Nest provider that continuously consumes a Redis Stream and publishes
 * normalized events to the GraphQL subscription layer.
 */
@Injectable()
export class SessionEventsStreamBridge implements OnModuleInit, OnModuleDestroy {
  private readonly log = new Logger(SessionEventsStreamBridge.name);
  private readonly redis = new IORedis(process.env.REDIS_URL!);
  private running = true;

  constructor(@Inject(SESSION_PUBSUB) private readonly pubsub: PubSubEngine) {}

  /**
   * Start a long-running polling loop using XREADGROUP.
   * - Uses a consumer group to coordinate with other instances (at-least-once semantics).
   * - BATCH: COUNT 32, BLOCK 5000ms for efficient consumption.
   * - On success: publish to PubSub and XACK the entry.
   * - On parsing/publication error: log and XACK (to avoid stuck entries).
   */
  private async startPolling(stream: string, group: string, consumer: string): Promise<void> {
    // Main consumption loop — stops when onModuleDestroy flips `running` to false
    while (this.running) {
      try {
        // Read from Redis Stream via consumer group with backpressure-friendly BLOCK
        const resRaw = await this.redis.xreadgroup(
          'GROUP',
          group,
          consumer,
          'COUNT',
          32,
          'BLOCK',
          5000,
          'STREAMS',
          stream,
          '>',
        );
        const res = resRaw as unknown as XReadGroupResult | null;
        // No new entries; continue waiting
        if (!res || res.length === 0) continue;

        // Iterate over streams and entries returned by XREADGROUP
        for (const [, entries] of res) {
          for (const [id, fields] of entries) {
            try {
              // Parse and validate payload; throws on invalid shape
              const payload = this.parsePayload(fields);
              // Publish to GraphQL subscription trigger; subscribers receive typed payload
              await this.pubsub.publish(TRIGGER_SESSION_EVENTS, payload);
              // Acknowledge the entry to mark it as processed for this group/consumer
              await this.redis.xack(stream, group, id);
            } catch (err) {
              this.log.error(`stream=${stream} id=${id} err=${(err as Error).message}`);
              // Acknowledge the entry to mark it as processed for this group/consumer
              await this.redis.xack(stream, group, id);
            }
          }
        }
      } catch (e) {
        const msg =
          typeof e === 'object' && e && 'message' in e ? String((e as Error).message) : '';
        this.log.warn(`xreadgroup error: ${msg}`);
        // Throttle retries on transient connection issues
        // 연결 불안정 시 과열 방지
        await new Promise(r => setTimeout(r, 500));
      }
    }
  }

  /**
   * Initialize consumer group (idempotent) and start the polling loop.
   * - Creates the group with MKSTREAM to ensure the stream exists.
   */
  async onModuleInit() {
    const stream = STREAM_SESSION_EVENTS;
    const group = 'gql-session-events';
    const consumer = `nest-${process.pid}`;

    // Create consumer group if it does not exist yet (idempotent pattern)
    // 컨슈머 그룹 생성 (있으면 통과)
    try {
      await this.redis.xgroup('CREATE', stream, group, '$', 'MKSTREAM');
    } catch (e: any) {
      const msg = typeof e === 'object' && e && 'message' in e ? String((e as Error).message) : '';
      // BUSYGROUP means the group already exists — safe to ignore
      if (!msg.includes('BUSYGROUP')) throw e;
    }

    // Fire-and-forget: run polling loop asynchronously
    void this.startPolling(stream, group, consumer);
  }

  /**
   * Convert flat Redis XADD field array into an object and parse `payload` JSON.
   * Validates and narrows the shape using Zod.
   */
  private parsePayload(fields: Array<string | Buffer>): SessionEvent {
    // Flatten fields: [k1, v1, k2, v2, ...] → { k1: v1, k2: v2 }
    const obj: Record<string, string> = {};
    for (let i = 0; i < fields.length; i += 2) {
      const k = String(fields[i]);

      obj[k] = String(fields[i + 1] ?? '');
    }
    // Deserialize the `payload` field; default to empty object when missing
    const raw = JSON.parse(obj.payload ?? '{}') as unknown;
    return SessionEventSchema.parse(raw);
  }

  /**
   * Signal the polling loop to stop and close the Redis connection gracefully.
   */
  onModuleDestroy() {
    this.running = false;
    this.redis.disconnect();
  }
}
