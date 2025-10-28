/**
 * IngestController (Gateway)
 * - Issues presigned PUT URLs for object storage uploads.
 * - Finalizes uploads by syncing object metadata into the DB.
 * - Provides a lightweight HEAD proxy for debugging/storage checks.
 * - Authenticated via JwtAuthGuard.
 */
// src/modules/ingest/ingest.controller.ts
import {
  BadRequestException,
  Body,
  Controller,
  Get,
  InternalServerErrorException,
  Logger,
  NotFoundException,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';

import { extname } from 'node:path';
import { randomUUID } from 'crypto';
import { lookup as mimeLookup } from 'mime-types';
import { S3ServiceException } from '@aws-sdk/client-s3';
import { ObjectStorageService } from '@/modules/infra/object-storage/object-storage.service';
import { IngestService } from '@/modules/ingest/ingest.service';
import { type AuthUser, CurrentUser } from '@/modules/auth/current-user.decorator';
import { FileStatus, FileVisibility } from '@/modules/ingest/gql/file.type';
import { FileMetadataZDto } from '@/modules/ingest/ingest.zod';

/** DTO for presign PUT request body. */
export class CreatePutUrlDto {
  filename!: string; // required
  bucket?: string;
  checksum!: string;
  size!: number;
}

// Allowed MIME types for uploads (server-side allowlist)
const ALLOWED_MIME = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'application/pdf',
  'text/plain',
  'text/markdown',
]);

const logger = new Logger('IngestController');

/**
 * REST endpoints for file ingest lifecycle.
 * All routes are prefixed with /v1/ingest and protected by JwtAuthGuard.
 */
@Controller('v1/ingest')
@UseGuards(JwtAuthGuard)
export class IngestController {
  constructor(
    private readonly client: ObjectStorageService,
    private readonly ingestService: IngestService,
  ) {}

  /**
   * POST /v1/ingest/presign/put
   * Create a presigned PUT URL for direct-to-object-storage upload.
   * - Validates filename and content-type (allowlist).
   * - Generates a user-scoped key: `users/{pns}/{uuid}`.
   * - Inserts a PENDING metadata row for tracking.
   * @returns signed URL + headers needed by the client.
   */
  @Post('presign/put')
  async presignPut(@CurrentUser() user: AuthUser, @Body() dto: CreatePutUrlDto) {
    if (!dto?.filename) {
      throw new BadRequestException('filename is required');
    }

    // Safely extract file extension (e.g., ".pdf")
    const ext = extname(dto.filename).toLowerCase(); // ".pdf"
    if (!ext) throw new BadRequestException('file extension is missing');

    // Infer MIME type from extension; fallback to octet-stream
    const mime = mimeLookup(ext) || 'application/octet-stream';
    logger.debug('mime', mime);
    // Enforce server-side MIME allowlist
    if (!ALLOWED_MIME.has(mime)) {
      throw new BadRequestException(`unsupported content type: ${mime}`);
    }

    // Build safe object key scoped by user namespace
    const publicNamespace = user.pns;
    const key = `users/${publicNamespace}/${randomUUID()}`;
    const putUrl = {
      ...(await this.client.createPutUrl({
        key,
        bucket: dto.bucket,
        contentType: mime,
        contentLength: dto.size,
        checksum: dto.checksum,
        expiresSec: 300,
      })),
      extension: ext,
      contentType: mime,
    };

    // Prepare DB metadata record (PENDING)
    const pendingMetadata: FileMetadataZDto = {
      bucket: putUrl.bucket,
      key: putUrl.key,
      filename: dto.filename,
      contentType: mime,
      // size: ContentLength,
      // etag: (ETag ?? '').replace(/"/g, ''),
      status: FileStatus.PENDING,
      visibility: FileVisibility.PRIVATE,
      ownerId: user.sub,
      extension: ext,
    };
    // Persist pending record so the system can reconcile after upload
    await this.ingestService.createPendingRecord(pendingMetadata);
    // Return presigned URL and additional meta used by the client
    return putUrl;
  }

  /**
   * POST /v1/ingest/complete
   * Finalize an upload by reading object metadata and updating the DB record.
   * - Validates presence of bucket/key.
   * - Reads object head (size, ETag, contentType, lastModified).
   * - Upserts DB record to READY and returns updated entry.
   */
  @Post('complete')
  @UseGuards(JwtAuthGuard)
  async completePost(
    @CurrentUser() user: AuthUser,
    @Body() body: { bucket: string; key: string; filename: string },
  ) {
    const { key, bucket, filename } = body;
    if (!key || !bucket) {
      throw new BadRequestException('key and bucket are required');
    }

    // Read object metadata from storage for DB sync
    const statObject = await this.client.statObject(bucket, key);
    logger.debug('completePost', { statObject: statObject });
    const { etag, size, lastModified, contentType } = statObject;

    // Build metadata payload for DB update
    const fileMetadata: FileMetadataZDto = {
      bucket,
      key,
      size,
      filename,
      contentType,
      etag: (etag ?? '').replace(/"/g, ''),
      status: FileStatus.READY,
      visibility: FileVisibility.PRIVATE,
      ownerId: user.sub,
      uploadedAt: lastModified,
      modifiedAt: lastModified,
    };

    // Update DB status to READY (create/update as needed)
    const updatedRecord = this.ingestService.upsertFileMetadataByKey(fileMetadata, user);

    // (Optional) Dispatch to worker for vectorization / downstream processing
    // await this.kafkaService.emit('file.ready', { key, bucket });

    // Respond with a human-readable message and the updated record
    return {
      message: 'File upload completed and status updated.',
      record: updatedRecord,
    };
  }

  /**
   * GET /v1/ingest/object/head?bucket=...&key=...
   * Proxy to object storage HEAD for debugging/verification.
   * - Normalizes common S3 errors into HTTP exceptions.
   */
  @Get('object/head')
  async headObject(@Query('bucket') bucket: string, @Query('key') key: string) {
    if (!bucket || !key) {
      throw new BadRequestException('bucket and key are required');
    }
    try {
      return await this.client.statObject(bucket, key);
    } catch (err: unknown) {
      // Map S3 SDK errors to HTTP-friendly exceptions
      if (err instanceof S3ServiceException) {
        const status = err.$metadata?.httpStatusCode;
        const name = err.name; // safe

        // Not found variants from S3
        if (status === 404 || name === 'NotFound' || name === 'NoSuchKey') {
          throw new NotFoundException('object not found');
        }
        // Preserve cause (optional): include name in message
        throw new InternalServerErrorException(`headObject failed: ${name}`);
      }

      // Generic Error -> 500 with message
      if (err instanceof Error) {
        throw new InternalServerErrorException(`headObject failed: ${err.message}`);
      }

      // Unknown error type
      throw new InternalServerErrorException('headObject failed');
    }
  }
}
