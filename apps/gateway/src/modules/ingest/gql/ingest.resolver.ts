// apps/gateway/src/graphql/resolvers/ingest.resolver.ts
import {
  Args,
  Mutation,
  Resolver,
  Subscription,
  Query,
  Field,
  ObjectType,
  Context,
  Int,
  ID,
} from '@nestjs/graphql';
import { PubSubEngine } from 'graphql-subscriptions';
import {
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
  UseGuards,
} from '@nestjs/common';
import { IngestService } from '@/modules/ingest/ingest.service';
import { DeleteFilePayload, FileType } from '@/modules/ingest/gql/file.type';
import { FileListType } from '@/modules/ingest/gql/file.type';
import { FileMetadataInput } from '@/modules/ingest/gql/file.type';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import { CurrentUser } from '@/modules/auth/current-user.decorator';
import type { FileListItem } from '@/modules/ingest/ingest.repository';
import { PUB_SUB } from '@/common/constants';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';
import { decodeCursor, encodeCursor } from '@/modules/infra/graphql/utils/cursor';

@ObjectType()
class FileEdge {
  @Field(() => FileListType)
  node!: FileListType;
  @Field(() => String, { nullable: true })
  cursor?: string | null;
}

@ObjectType()
class FileConnection {
  @Field(() => [FileEdge])
  edges!: FileEdge[];

  @Field(() => PageInfo)
  pageInfo!: PageInfo;
}

/**
 * IngestResolver
 * - Handles file registration, listing, and deletion through GraphQL.
 * - Authenticated via JwtAuthGuard and enforces user ownership.
 * - Provides subscription for file status updates (upload, vectorization, deletion).
 */
@Resolver()
@Injectable()
@UseGuards(JwtAuthGuard)
export class IngestResolver {
  /**
   * Map repository row (snake_case) → GraphQL entity (camelCase).
   * Converts timestamps to JS Date objects for schema compliance.
   */
  private toFileListEntity = (r: FileListItem): FileListType => {
    return {
      id: r.id,
      filename: r.filename,
      contentType: r.content_type ?? null,
      size: r.size ?? null,
      status: r.status as any,
      visibility: r.visibility as any,
      uploadedAt: r.uploaded_at ? new Date(r.uploaded_at) : null,
      createdAt: new Date(r.created_at),
    };
  };

  constructor(
    private readonly ingestService: IngestService,
    @Inject(PUB_SUB) private readonly pubSub: PubSubEngine,
  ) {}

  /**
   * Query: files
   * - Returns paginated list of uploaded files for the authenticated user.
   * - Implements keyset pagination using `after` cursor.
   * - Enforces user context via @CurrentUser.
   */
  @Query(() => FileConnection, { name: 'files', description: 'List files' })
  async listMyFiles(
    @Args('first', { type: () => Int }) first: number,
    @Args('after', { type: () => String, nullable: true })
    after?: string | null,
    @Context() ctx?: any,
    @CurrentUser() user?: { sub: string },
  ): Promise<FileConnection> {
    // Extract current user id from JWT payload
    const userId = user?.sub;
    if (!userId) {
      throw new Error('Unauthorized');
    }

    type FileCursor = {
      uploadedAt: string | null;
      createdAt: string;
      id: string;
    };

    // Decode pagination cursor
    const cursorObj = decodeCursor<FileCursor>(after);
    // Fetch file list from service
    const rows = await this.ingestService.listForUser(userId, first, cursorObj);
    // Determine pagination cursors and flags
    const hasNextPage = rows.length > first;
    const items = hasNextPage ? rows.slice(0, first) : rows;
    const startCursor = items.length ? encodeCursor(items[0]) : null;
    const endCursor = items.length ? encodeCursor(items[items.length - 1]) : null;
    const hasPreviousPage = Boolean(after);

    // Build connection response with edges + pageInfo
    return {
      edges: items.map(i => ({
        cursor: encodeCursor(i),
        node: this.toFileListEntity(i),
      })),
      pageInfo: { startCursor, endCursor, hasNextPage, hasPreviousPage },
    };
  }

  /**
   * Mutation: registerFile
   * - Creates a pending file metadata record before upload.
   * - Used by clients to initialize upload URLs and metadata tracking.
   */
  @Mutation(() => FileType)
  registerFile(@Args('input') input: FileMetadataInput) {
    return this.ingestService.createPendingRecord(input);
  }

  /**
   * Mutation: deleteFile
   * - Validates ownership and enqueues a delete job.
   * - Marks file status as 'deleting' and triggers async cleanup.
   */
  @Mutation(() => DeleteFilePayload)
  async deleteFile(
    @Args('fileId', { type: () => ID }) fileId: string,
    @CurrentUser() user: { sub: string },
  ): Promise<DeleteFilePayload> {
    // Fetch owner of the file for authorization
    const userId = user.sub;
    const ownerId = await this.ingestService.getFileOwnerId(fileId);
    // Not found → 404
    if (!ownerId) throw new NotFoundException('File not found');
    // Ownership mismatch → 403
    if (ownerId !== userId) throw new ForbiddenException('You do not own this file');

    // Soft delete flag update in DB
    await this.ingestService.markDeleting(fileId);

    // Enqueue background deletion job via worker
    const jobId = await this.ingestService.enqueueDelete({
      fileId,
      userId,
      reason: 'graphql.deleteFile',
    });

    // Return immediate success with job reference
    return { ok: true, fileId, message: jobId };
  }

  /**
   * Subscription: fileStatusChanged
   * - Publishes file status updates (e.g., pending → uploaded → vectorized → deleted).
   * - Filters events server-side to ensure only matching fileId is streamed to the client.
   */
  @Subscription(() => FileType, {
    filter: (
      payload: { fileStatusChanged?: { id?: unknown } },
      variables: { fileId?: unknown },
    ) => {
      // Ensure provided fileId variable is valid string
      const fileId = typeof variables?.fileId === 'string' ? variables.fileId : null;
      if (!fileId) return false;

      // Validate payload structure
      const payloadId = payload?.fileStatusChanged?.id;
      if (typeof payloadId !== 'string') return false;

      // Allow only matching fileId events
      return payloadId === fileId;
    },
  })
  fileStatusChanged(@Args('fileId') fileId: string) {
    return (
      this.pubSub as unknown as {
        asyncIterator<T>(trigger: string): AsyncIterable<T>;
      }
    ).asyncIterator<FileType>(`file-status:${fileId}`);
  }
}
