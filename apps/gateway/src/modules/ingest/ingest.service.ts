/**
 * IngestService
 * - Orchestrates file ingest lifecycle: registration (PENDING), READY upsert, and deletion.
 * - Coordinates with IngestRepository (Postgres), Object Storage, and Kafka workers.
 * - All public methods are designed to be called from controllers/resolvers with Auth context.
 */
import { Injectable, Logger } from '@nestjs/common';
import { FileMetadataRegister, FileMetadataUpsert } from '@/modules/ingest/ingest.zod';
import { FileStatusZ, type FileVisibility as FileVisibilityValue } from '@talkie/types-zod/';
import { FileStatus, FileVisibility } from '@talkie/types-zod';
import { IngestRepository } from '@/modules/ingest/ingest.repository';
import { AuthUser } from '@/modules/auth/current-user.decorator';
import { KafkaService } from '@/modules/infra/kafka/kafka.service';
import type { Request, Response } from 'express';
import Redis from 'ioredis';
import {
  IngestEvent,
  IngestEventType,
  IngestEventZ,
  topicForUserFiles,
} from '@talkie/events-contracts';
import { channel } from 'node:diagnostics_channel';

/** Core service for file ingest flows (create, list, mark deleting, enqueue jobs). */
@Injectable()
export class IngestService {
  private readonly logger = new Logger(IngestService.name);
  private redis: Redis;
  constructor(
    private readonly ingestRepo: IngestRepository,
    private readonly kafka: KafkaService,
  ) {
    this.redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379');
  }

  /**
   * Create a PENDING metadata record prior to upload.
   * - Upserts by (bucket, key) to allow idempotent presign flows.
   * - Sets minimal fields required to reconcile after upload completion.
   * @returns input merged with normalized status (PENDING)
   */
  async createPendingRecord(input: FileMetadataRegister) {
    const { bucket, key, filename, ownerId, contentType } = input;

    // Persist minimal metadata for reconciliation after client upload
    await this.ingestRepo.upsertByKey({
      bucket,
      key,
      filename,
      ownerId,
      contentType,
      visibility: FileVisibility.Private,
      status: FileStatus.Pending,
      meta: { source: 'upload' },
    });
    return { ...input, status: FileStatus.Pending };
  }

  /**
   * Upsert metadata by (bucket, key) and optionally emit a worker job.
   * - When status transitions to READY, produces `ingest.request` for vectorization/indexing.
   * - Uses user context for job ownership/audit trail.
   */
  async upsertFileMetadataByKey(input: FileMetadataUpsert, user: AuthUser) {
    // Normalize and validate status using Zod schema
    const parsedStatus = FileStatusZ.parse(input.status);
    const { bucket, key, status, size, etag } = input;
    const userId = user.sub;

    // Update status/size/etag and capture server-side timestamp
    const updatedAt = await this.ingestRepo.updateIndexStatusByKey({
      bucket,
      key,
      status,
      size,
      etag,
    });

    // On READY status, kick off downstream processing via Kafka
    if (parsedStatus === FileStatus.Ready) {
      // Re-fetch to obtain DB id and canonical filename
      const file = await this.ingestRepo.getByKey(bucket, key);
      if (!file) {
        throw new Error(`File not found: ${bucket}/${key}`);
      }
      const { id: fileId } = file;
      const jobId = crypto.randomUUID();
      const payload = {
        jobId: jobId,
        userId: userId,
        fileId: fileId,
        filename: file.filename,
        bucket: file.bucket,
        key: file.key,
      };

      const redisEvent: IngestEvent = {
        v: 1,
        type: IngestEventType.REGISTERED,
        payload: {
          id: fileId,
          contentType: file.content_type,
          filename: file.filename,
          size: size,
          status: parsedStatus,
          visibility: file.visibility,
          uploadedAt: updatedAt ?? new Date(),
          createdAt: updatedAt ?? new Date(),
        },
        ts: Date.now(),
      };

      const ok = IngestEventZ.safeParse(redisEvent);
      if (!ok.success) {
        this.logger.warn('publish aborted', ok.error);
        return;
      }
      const channel = topicForUserFiles(userId);
      await this.redis.publish(channel, JSON.stringify(ok.data));
      // Produce job for background worker (idempotent by jobId)
      await this.kafka.produce('ingest.request', payload, jobId);
    }

    // Return lightweight status+timestamp update for clients
    return {
      key,
      status: parsedStatus,
      updatedAt: updatedAt ?? new Date(),
    };
  }

  /**
   * Update visibility for a file by its id. Ownership/authorization is enforced upstream.
   * Publishes an SSE-friendly event to the user's channel if user context is provided.
   */
  async updateVisibilityById(fileId: string, visibility: FileVisibilityValue, userId: string) {
    await this.ingestRepo.updateVisibility(fileId, visibility);

    // Optionally notify client(s) via Redis Pub/Sub if user context exists
    try {
      if (userId) {
        const redisEvent: IngestEvent = {
          v: 1,
          type: IngestEventType.VISIBILITY_CHANGED,
          payload: {
            id: fileId,
            prev: visibility,
            next: visibility,
          },
          ts: Date.now(),
        };
        await this.redis.publish(topicForUserFiles(userId), JSON.stringify(redisEvent));
      }
    } catch (err) {
      this.logger.warn(
        `updateVisibilityById: publish failed: ${String((err as Error)?.message ?? err)}`,
      );
    }
  }

  /**
   * List files for a given user with keyset pagination.
   * - Delegates to repository for query & cursor handling.
   */
  async listForUser(
    userId: string,
    first: number,
    after: { uploadedAt: string | null; createdAt: string; id: string } | null,
  ) {
    return this.ingestRepo.listRowsForUser(userId, first, after); // Pass-through to repository (handles pagination)
  }

  /** Resolve file owner for authorization checks. */
  async getFileOwnerId(fileId: string): Promise<string | null> {
    return this.ingestRepo.getOwnerId(fileId);
  }

  /** Soft-delete: mark file as deleting; worker performs physical/object cleanup. */
  async markDeleting(fileId: string) {
    await this.ingestRepo.markDeleting(fileId);
  }

  /**
   * Enqueue deletion job for a file (async cleanup).
   * - Emits `ingest.delete` with correlation jobId.
   * - `reason` helps downstream auditing/diagnostics.
   */
  async enqueueDelete(input: { fileId: string; userId: string; reason: string }) {
    // Generate correlation id for traceability
    const jobId = crypto.randomUUID();
    const payload = {
      jobId,
      userId: input.userId,
      fileId: input.fileId,
      reason: input.reason ?? 'graphql.deleteFile',
    };
    const redisEvent: IngestEvent = {
      v: 1,
      type: IngestEventType.DELETED,
      payload: {
        id: input.fileId,
        deletedAt: new Date().toISOString(),
      },
      ts: Date.now(),
    };
    await this.redis.publish(topicForUserFiles(input.userId), JSON.stringify(redisEvent));
    // Publish delete request to worker topic
    await this.kafka.produce('ingest.delete', payload, jobId);
    // Return job handle to the caller for SSE follow-up
    return jobId;
  }

  async streamUserEvents(req: Request, res: Response, userId: string): Promise<void> {
    // 1) SSE headers
    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    (res as any).flushHeaders?.();

    const write = (s: string) => res.write(s);
    // client auto-retry + heartbeat
    write(`retry: 3000\n`);
    const hb = setInterval(() => write(`event: ping\ndata: {}\n\n`), 15000);

    // 2) Redis Pub/Sub: user-scope channel
    const reader = this.redis.duplicate();
    const channel = topicForUserFiles(userId);

    // Error propagation
    const onError = (err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      try {
        write(`event: error\ndata: ${JSON.stringify({ message })}\n\n`);
      } catch (writeErr) {
        this.logger.warn(
          `onError: failed to write SSE error frame: ${String((writeErr as Error)?.message ?? writeErr)}`,
        );
      }
      void cleanup();
    };
    reader.on('error', onError);

    /**
     * Bridge contract:
     * - Publisher must send JSON string: { v:number, ts:number, type:string, ... }
     * - We **parse once** and map SSE `event:` to payload.type (fallback to 'ingest').
     * - Gateway does not mutate payload; it only frames SSE correctly.
     */
    // 3) Subscribe and start streaming

    // Strict router: only emit when a typed domain event is present, no fallback
    const onMessage = (_ch: string, msg: string) => {
      try {
        const parsed = JSON.parse(msg);
        const t = parsed?.type;
        // Emit only domain-typed events (e.g., 'file.registered', 'file.status.changed', ...)
        if (typeof t === 'string' && t.length > 0) {
          write(`event: ${t}\n`);
          write(`data: ${msg}\n\n`);
        } else {
          // No type → handled by legacy emitter elsewhere; avoid double frames
          return;
        }
      } catch {
        // Non-JSON payloads are ignored here to prevent duplicate 'status' frames
        return;
      }
    };

    try {
      await reader.subscribe(channel);
      reader.on('message', onMessage);
    } catch (e) {
      onError(e);
      return;
    }

    // 4) Idempotent cleanup bound to multiple termination signals
    let closed = false;
    const cleanup = async () => {
      if (closed) return;
      closed = true;
      clearInterval(hb);
      try {
        reader.off('message', onMessage);
      } catch (err) {
        this.logger.warn(`cleanup: failed to remove message listener: ${String(err)}`);
      }
      try {
        reader.removeListener('error', onError);
      } catch (err) {
        this.logger.warn(`cleanup: failed to remove error listener: ${String(err)}`);
      }
      try {
        // Ensure unsubscribe resolves and does not reject unhandled
        await reader.unsubscribe(channel);
      } catch (err) {
        this.logger.warn(`cleanup: failed to unsubscribe ${channel}: ${String(err)}`);
      }
      try {
        reader.disconnect();
      } catch (err) {
        this.logger.warn(`cleanup: failed to disconnect redis reader: ${String(err)}`);
      }
      try {
        if (typeof (res as any).writableEnded === 'boolean' && (res as any).writableEnded) {
          // already ended; skip
        } else {
          res.end();
        }
      } catch (err) {
        this.logger.warn(`cleanup: response end failed: ${String(err)}`);
      }
    };

    // Wrap async cleanup in a sync listener to satisfy void-return expectations
    const tidy = () => {
      void cleanup();
    };

    req.on('close', tidy);
    req.on('aborted', tidy as any);
    res.on?.('close', tidy);
    res.on?.('finish', tidy);
    res.on?.('error', tidy as any);
  }
}
