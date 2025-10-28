/**
 * Custom JWT authentication guard compatible with both HTTP and GraphQL contexts.
 * Extends NestJS Passport AuthGuard('jwt') to properly extract the request object
 * when used in GraphQL resolvers.
 */
import { ExecutionContext, Injectable } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { GqlExecutionContext } from '@nestjs/graphql';
import type { Request } from 'express';

/**
 * JwtAuthGuard overrides getRequest to support both HTTP and GraphQL execution contexts.
 */
@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {
  getRequest(context: ExecutionContext): Request {
    // Case 1: Standard HTTP request — use switchToHttp to extract the request.
    // HTTP 요청이면 기본 switchToHttp 사용
    if (context.getType() === 'http') {
      return context.switchToHttp().getRequest<Request>();
    }
    // Case 2: GraphQL request — use GqlExecutionContext to access the underlying Express req.
    // ★ GraphQL 컨텍스트에서 req 뽑아오기
    const ctx = GqlExecutionContext.create(context);
    const { req } = ctx.getContext<{ req: Request }>();

    return req;
  }
}
