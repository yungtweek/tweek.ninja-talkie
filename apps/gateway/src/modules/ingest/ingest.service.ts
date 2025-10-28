/**
 * IngestService
 * - Orchestrates file ingest lifecycle: registration (PENDING), READY upsert, and deletion.
 * - Coordinates with IngestRepository (Postgres), Object Storage, and Kafka workers.
 * - All public methods are designed to be called from controllers/resolvers with Auth context.
 */
import { Injectable } from '@nestjs/common';
import { FileMetadataSchema, FileMetadataZDto } from '@/modules/ingest/ingest.zod';
import { FileStatus } from '@/modules/ingest/gql/file.type';
import { IngestRepository } from '@/modules/ingest/ingest.repository';
import { AuthUser } from '@/modules/auth/current-user.decorator';
import { KafkaService } from '@/modules/infra/kafka/kafka.service';

/** Core service for file ingest flows (create, list, mark deleting, enqueue jobs). */
@Injectable()
export class IngestService {
  constructor(
    private readonly ingestRepo: IngestRepository,
    private readonly kafka: KafkaService,
  ) {}

  /**
   * Create a PENDING metadata record prior to upload.
   * - Upserts by (bucket, key) to allow idempotent presign flows.
   * - Sets minimal fields required to reconcile after upload completion.
   * @returns input merged with normalized status (PENDING)
   */
  async createPendingRecord(input: FileMetadataZDto) {
    const { bucket, key, filename, ownerId, contentType } = input;

    // Persist minimal metadata for reconciliation after client upload
    await this.ingestRepo.upsertByKey({
      bucket,
      key,
      filename,
      ownerId,
      contentType,
      // size,
      // etag,
      visibility: 'private',
      status: 'pending',
      meta: { source: 'upload' },
    });
    return { ...input, status: FileStatus.PENDING };
  }

  /**
   * Upsert metadata by (bucket, key) and optionally emit a worker job.
   * - When status transitions to READY, produces `ingest.request` for vectorization/indexing.
   * - Uses user context for job ownership/audit trail.
   */
  async upsertFileMetadataByKey(input: FileMetadataZDto, user: AuthUser) {
    // Normalize and validate status using Zod schema
    const parsedStatus = FileMetadataSchema.shape.status.parse(input.status);
    const { bucket, key, status, size, etag } = input;

    // Update status/size/etag and capture server-side timestamp
    const updatedAt = await this.ingestRepo.updateIndexStatusByKey({
      bucket,
      key,
      status,
      size,
      etag,
    });

    // On READY status, kick off downstream processing via Kafka
    if (parsedStatus === FileStatus.READY) {
      // Re-fetch to obtain DB id and canonical filename
      const file = await this.ingestRepo.getByKey(bucket, key);
      if (!file) {
        throw new Error(`File not found: ${bucket}/${key}`);
      }
      const { id: fileId } = file;
      const jobId = crypto.randomUUID();
      const payload = {
        jobId: jobId,
        userId: user.sub,
        fileId: fileId,
        filename: file.filename,
        bucket: file.bucket,
        key: file.key,
      };

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
    // Publish delete request to worker topic
    await this.kafka.produce('ingest.delete', payload, jobId);
    // Return job handle to the caller for SSE follow-up
    return jobId;
  }
}
