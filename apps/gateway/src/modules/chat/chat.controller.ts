// src/modules/chat/chat.controller.ts
import { Controller, Post, Body, Sse, MessageEvent, Param, Req, UseGuards } from '@nestjs/common';
import type { Request } from 'express';
import { ChatService } from './chat.service';
import { ZodValidationPipe } from 'nestjs-zod';
import { EnqueueSchema } from '@/modules/chat/dto/enqueue.zod';
import type { EnqueueInput } from '@/modules/chat/dto/enqueue.zod';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import { CurrentUser } from '@/modules/auth/current-user.decorator';
import type { AuthUser } from '@/modules/auth/current-user.decorator';

/**
 * ChatController (Gateway)
 * - Handles enqueueing chat jobs and exposing Server-Sent Events (SSE) streams.
 * - Authenticated via JwtAuthGuard; user context is injected with @CurrentUser.
 * - Validation is performed with ZodValidationPipe on request DTOs.
 */
@Controller('v1/chat')
export class ChatController {
  constructor(private readonly chat: ChatService) {}

  /**
   * POST /v1/chat
   * Enqueue a chat job and return identifiers.
   * - Validates body with ZodValidationPipe (EnqueueSchema).
   * - Requires authentication; uses AuthUser for ownership/attribution.
   */
  @Post()
  @UseGuards(JwtAuthGuard)
  async post(
    @Body(new ZodValidationPipe(EnqueueSchema)) dto: EnqueueInput, // Validate DTO at the boundary (schema-enforced) — // ✅ Only this endpoint uses the Zod validation pipe
    @CurrentUser() user: AuthUser,
  ) {
    return this.chat.enqueue(dto, user); // { sessionId, jobId }
  }

  /**
   * SSE /v1/chat/stream/:jobId
   * Stream model output tokens and intermediate events for a specific job.
   * - Reads Last-Event-ID header to resume from the last acknowledged event.
   * - Delegates observable creation to ChatService.chatStream().
   */
  @Sse('stream/:jobId')
  @UseGuards(JwtAuthGuard)
  stream(
    @Param('jobId') jobId: string,
    @Req() req: Request,
    @CurrentUser() user: AuthUser,
  ): import('rxjs').Observable<MessageEvent> {
    // Support SSE reconnection by honoring the Last-Event-ID header (default to "0-0")
    const lastEventId = (req.headers['last-event-id'] as string | undefined) ?? '0-0';
    // Delegate to service: ChatService should return Observable<MessageEvent>
    return this.chat.chatStream(jobId, user, lastEventId);
  }

  /**
   * SSE /v1/chat/session/events/:jobId
   * Stream session-scoped lifecycle events (e.g., CREATED/UPDATED/DELETED) related to a job.
   * - Reads Last-Event-ID header for resumable delivery.
   * - Delegates to ChatService.sessionEvents().
   */
  @Sse('session/events/:jobId')
  @UseGuards(JwtAuthGuard)
  sessionEvents(
    @Param('jobId') jobId: string,
    @Req() req: Request,
    @CurrentUser() user: AuthUser,
  ): import('rxjs').Observable<MessageEvent> {
    // Support SSE reconnection by honoring the Last-Event-ID header (default to "0-0")
    const lastEventId = (req.headers['last-event-id'] as string | undefined) ?? '0-0';
    // Delegate to service: ChatService should return Observable<MessageEvent>
    return this.chat.sessionEvents(jobId, user, lastEventId);
  }
}
