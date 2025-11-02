// apps/gateway/src/modules/chat/gql/chat.resolver.ts
import { Args, ID, Int, Parent, Query, ResolveField, Resolver } from '@nestjs/graphql';
import { ChatRepository } from '@/modules/chat/chat.repository';
import { Message, MessageConnection, MessageEdge, ChatSession } from './chat.type';
import { toCursor, fromCursor } from '../../infra/graphql/utils/cursor';
import { z } from 'zod';
import { ForbiddenException, Injectable, NotFoundException, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import { CurrentUser } from '@/modules/auth/current-user.decorator';
import { ChatMessageZ } from '@talkie/types-zod';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';

@Resolver(() => ChatSession)
@Injectable()
@UseGuards(JwtAuthGuard)
/**
 * ChatResolver
 * - Serves ChatSession queries and paginated message retrieval.
 * - Performs ownership validation for protected access.
 * - Authenticated via JwtAuthGuard.
 */
export class ChatResolver {
  constructor(private readonly chatRepository: ChatRepository) {}

  /**
   * Query: chatSession
   * - Returns a hydrated ChatSession node by ID after validating ownership.
   * - The messages field is resolved separately (cursor-based).
   */
  @Query(() => ChatSession)
  async chatSession(
    @Args('id', { type: () => ID }) id: string,
    @CurrentUser() user: { sub: string },
  ): Promise<ChatSession> {
    // Load session meta and validate ownership
    const meta = await this.chatRepository.getSessionMeta(id);
    if (!meta) throw new NotFoundException('Session not found');
    if (meta.userId !== user.sub) throw new ForbiddenException('Not your session');

    // Return hydrated ChatSession (messages are resolved via ResolveField)
    return {
      id,
      title: meta.title ?? null,
      createdAt: meta.createdAt,
      updatedAt: meta.updatedAt,
    } as ChatSession;
  }

  /**
   * ResolveField: messages
   * - Returns paginated chat messages for a specific session.
   * - Ensures that the current user owns the session before accessing data.
   *
   * Pagination:
   *   - Supports cursor-based pagination (forward-only).
   *   - Uses `before` cursor and `first` limit for fetching messages.
   *
   * Ownership:
   *   - getUserId(sessionId) → verifies session owner matches the current user.
   */
  @ResolveField(() => MessageConnection)
  async messages(
    @Parent() parent: ChatSession,
    @Args('first', { type: () => Int, nullable: true }) first?: number,
    @Args('before', { nullable: true }) before?: string,
  ): Promise<MessageConnection> {
    const beforeIdx = fromCursor(before);
    const sessionId = parent.id;

    // Retrieve messages for the session with pagination options
    const rawRows = await this.chatRepository.listMessagesBySession(sessionId, {
      first: first ?? 50,
      before: beforeIdx,
    });
    // Validate message rows with Zod schema
    const rows = z.array(ChatMessageZ).parse(rawRows);

    // Build message edges for GraphQL connection structure
    const edges: MessageEdge[] = rows.map(r => {
      const sourcesJson =
        r.sourcesJson !== null && r.sourcesJson !== undefined
          ? JSON.stringify(r.sourcesJson)
          : null;

      return {
        node: {
          id: r.id,
          role: r.role,
          content: r.content,
          turn: r.turn,
          messageIndex: r.messageIndex,
          sourcesJson,
        } as Message,
        cursor: toCursor(r.messageIndex),
      };
    });

    // Return paginated connection result following Relay spec
    return {
      edges,
      pageInfo: {
        // Previous page exists if a `before` cursor was provided
        hasPreviousPage: Boolean(before),
        // Next page is conservatively inferred from the page size
        hasNextPage: edges.length >= (first ?? 50),
        startCursor: edges[0]?.cursor ?? null,
        endCursor: edges[edges.length - 1]?.cursor ?? null,
      } as PageInfo,
    };
  }
}
