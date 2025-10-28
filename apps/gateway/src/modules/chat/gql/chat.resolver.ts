// apps/gateway/src/graphql/resolvers/chat.resolver.ts
import { Args, ID, Int, Parent, Query, ResolveField, Resolver } from '@nestjs/graphql';
import { ChatRepository } from '@/modules/chat/chat.repository';
import { Message, MessageConnection, MessageEdge, ChatHistory, ChatSession } from './chat.type';
import { toCursor, fromCursor } from '../../infra/graphql/utils/cursor';
import { z } from 'zod';
import { ForbiddenException, Injectable, NotFoundException, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import { CurrentUser } from '@/modules/auth/current-user.decorator';
import { ChatMessageZ } from '@tweek/types-zod';
import { PageInfo } from '@/modules/infra/graphql/types/page-info.type';

@Resolver(() => ChatHistory)
@Injectable()
@UseGuards(JwtAuthGuard)
/**
 * ChatResolver
 * - Handles chat history queries per session.
 * - Performs ownership validation and paginated message retrieval.
 * - Authenticated via JwtAuthGuard.
 */
export class ChatResolver {
  constructor(private readonly chatRepository: ChatRepository) {}

  /**
   * Entry point query that initializes ChatHistory object by session ID.
   * Returns a lightweight ChatHistory wrapper containing the target session.
   */
  @Query(() => ChatHistory)
  chatHistory(@Args('id', { type: () => ID }) id: string): ChatHistory {
    return {
      session: { id } as ChatSession,
    } as ChatHistory;
  }

  /**
   * ResolveField: session
   * - Ensures the parent ChatHistory contains a valid ChatSession reference.
   */
  @ResolveField(() => ChatSession)
  session(@Parent() parent: ChatHistory): ChatSession {
    // parent.session may already be present; ensure it includes at least the id
    return parent.session;
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
   *   - getUserId(sessionId) → verifies session owner matches current user.
   */
  @ResolveField(() => MessageConnection)
  async messages(
    @Parent() parent: ChatHistory,
    @CurrentUser() user: { sub: string },
    @Args('first', { type: () => Int, nullable: true }) first?: number,
    @Args('before', { nullable: true }) before?: string,
  ): Promise<MessageConnection> {
    // Extract current user ID from JWT payload
    const userId = user.sub;
    const beforeIdx = fromCursor(before);
    const sessionId = parent.session.id;
    // Verify that the current user owns the requested chat session
    const ownerId = await this.chatRepository.getUserId(sessionId);
    if (!ownerId) throw new NotFoundException('Session not found');
    if (ownerId !== userId) throw new ForbiddenException('You do not own this file');
    // Retrieve messages for the session with pagination options
    const rawRows = await this.chatRepository.listMessagesBySession(userId, sessionId, {
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
        hasPreviousPage: edges.length > 0,
        startCursor: edges[0]?.cursor,
        endCursor: edges[edges.length - 1]?.cursor,
      } as PageInfo,
    };
  }
}
