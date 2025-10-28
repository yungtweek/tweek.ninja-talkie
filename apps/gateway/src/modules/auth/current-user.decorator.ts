/**
 * Custom parameter decorator to inject the authenticated user into controllers or GraphQL resolvers.
 * Works for both HTTP and GraphQL contexts.
 */
import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { Request } from 'express';
import { GqlExecutionContext } from '@nestjs/graphql';

/**
 * Represents the authenticated user payload extracted from JWT.
 * Mirrors the structure of JwtPayload but limited to fields required by the app layer.
 */
export interface AuthUser {
  pns: string;
  sub: string;
  username: string;
  email?: string;
  role?: string;
}

/**
 * CurrentUser decorator extracts the `user` object from either:
 *  - HTTP requests (via `req.user` set by Passport JwtAuthGuard)
 *  - GraphQL requests (via context.req.user)
 *
 * Usage:
 * ```ts
 * @CurrentUser() user: AuthUser
 * ```
 */
export const CurrentUser = createParamDecorator(
  (_data: unknown, ctx: ExecutionContext): AuthUser | null => {
    const type = ctx.getType<string>();

    // Case 1: Standard HTTP controller request
    if (type === 'http') {
      const req = ctx.switchToHttp().getRequest<Request & { user?: AuthUser }>();
      return req.user ?? null;
    }

    // Case 2: GraphQL resolver context
    // Requires GraphQLModule to pass `req` in context (see forRoot example)
    const gctx = GqlExecutionContext.create(ctx);
    const { req } = gctx.getContext<{ req: Request & { user?: AuthUser } }>();
    return req?.user ?? null;
  },
);
