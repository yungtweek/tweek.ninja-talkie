import {
  Args,
  ID,
  Int,
  Query,
  Resolver,
  Subscription,
  registerEnumType,
  Mutation,
} from '@nestjs/graphql';
import {
  ForbiddenException,
  Inject,
  Injectable,
  Logger,
  NotFoundException,
  UseGuards,
} from '@nestjs/common';
import { CurrentUser } from '@/modules/auth/current-user.decorator';
import { ChatRepository } from '@/modules/chat/chat.repository';
import {
  ChatSessions,
  DeleteChatSessionResult,
  SessionEvent,
} from '@/modules/chat/gql/session.type';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import { ChatSessionsZ } from '@tweek/types-zod';
import { SESSION_PUBSUB } from '@/modules/infra/pubsub/pubsub.module';
import { PubSubEngine } from 'graphql-subscriptions';

// --- Realtime session event payloads ---
export enum SessionEventType {
  CREATED = 'CREATED',
  UPDATED = 'UPDATED',
  DELETED = 'DELETED',
}
registerEnumType(SessionEventType, { name: 'SessionEventType' });

/**
 * ChatSessionResolver
 * - Handles chat session queries, deletions, and realtime subscription events.
 * - Enforces user ownership for sensitive mutations.
 * - Authenticated via JwtAuthGuard.
 */
@Resolver(() => ChatSessions)
@UseGuards(JwtAuthGuard)
@Injectable()
export class ChatSessionResolver {
  constructor(
    @Inject(ChatRepository)
    private readonly chatRepository: ChatRepository,
    @Inject(SESSION_PUBSUB) private pubSub: PubSubEngine,
  ) {}

  /**
   * Query: chatSessions
   * - Returns a paginated list of chat sessions for the authenticated user.
   * - Implements keyset pagination using `after` cursor.
   * - Default limit: 50, max: 100.
   */
  @Query(() => [ChatSessions])
  async chatSessions(
    @CurrentUser() user: { sub: string },
    @Args('first', { type: () => Int, nullable: true }) first?: number,
    @Args('after', { type: () => String, nullable: true }) after?: string,
  ) {
    // Determine pagination limit (default 50, capped at 100)
    const limit = Math.min(first ?? 50, 100);

    // Retrieve sessions belonging to the current user (sorted by recent)
    const rows = await this.chatRepository.listSessionsByUser(user.sub, {
      first: limit,
      after,
    });

    // Validate repository response shape with Zod
    const parsedResult = ChatSessionsZ.array().safeParse(rows);
    if (!parsedResult.success) {
      // 스키마와 불일치 시 빈 배열 반환 (로그 등은 서비스 레벨에서 처리)
      return [];
    }
    return parsedResult.data;
  }

  /**
   * Mutation: deleteChatSession
   * - Performs ownership validation before marking session as deleting.
   * - Emits outbox event for async cleanup (planned).
   * - Returns immediate soft-delete result to client.
   */
  @Mutation(() => DeleteChatSessionResult)
  async deleteChatSession(
    @Args('sessionId', { type: () => ID }) sessionId: string,
    @CurrentUser() user: { sub: string },
  ): Promise<DeleteChatSessionResult> {
    const userId = user.sub;
    // Check who owns this session
    const ownerId = await this.chatRepository.getUserId(sessionId);
    // Enforce ownership: only owner can delete
    if (!ownerId) throw new NotFoundException('Session not found');
    if (ownerId !== userId) throw new ForbiddenException('You do not own this file');

    // Soft-delete flag update in database
    await this.chatRepository.markSessionDeleting(sessionId);

    // TODO: Emit outbox event (SESSION_DELETED)
    // TODO 아웃 박스 처리
    // await this.chatRepository.insertOutboxEvent(
    //   'SESSION_DELETED',
    //   sessionId, // key
    //   { user_id: userId, session_id: sessionId }, // payload
    // );
    return { ok: true, status: 'deleting', sessionId: sessionId };
  }

  /**
   * Subscription: sessionEvents
   * - Publishes realtime updates for session lifecycle events (CREATED, UPDATED, DELETED).
   * - Filters server-side to ensure only events belonging to the current user are delivered.
   */
  @Subscription(() => SessionEvent, {
    resolve: (v: SessionEvent) => v,
    // 🔐 서버단 필터: 본인(userId) 이벤트만 통과
    filter: (payload: SessionEvent, _vars, ctx) => {
      // Extract current user ID from GraphQL context (supports both HTTP and WS)
      const currentUserId: string | undefined = ctx?.req?.user?.sub ?? ctx?.user?.sub;
      // Allow only events where userId matches the current user
      return Boolean(payload?.userId) && payload.userId === currentUserId;
    },
  })
  sessionEvents() {
    new Logger('ChatSessionResolver').debug('sessionEvents');
    return this.pubSub.asyncIterableIterator(
      'sessionEvents',
    ) as AsyncIterableIterator<SessionEvent>;
  }
}
