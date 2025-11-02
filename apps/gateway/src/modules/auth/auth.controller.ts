// src/modules/auth/auth.controller.ts
import {
  Body,
  Controller,
  Post,
  BadRequestException,
  UseGuards,
  Req,
  HttpCode,
  Get,
} from '@nestjs/common';
import { Request } from 'express';
import { AuthService } from './auth.service';
import { RefreshJwtAuthGuard } from '@/modules/auth/jwt-refresh.guard';
import { JwtAuthGuard } from '@/modules/auth/jwt.guard';
import type { AuthViewZod, MeViewZod } from '@talkie/types-zod';
import { MeViewZ } from '@talkie/types-zod';
import type { ZodType } from 'zod';

/**
 * Data Transfer Object for login requests.
 * Accepts either identifier, username, or email along with a password.
 */
type LoginDto = {
  identifier?: string;
  username?: string;
  email?: string;
  password: string;
};

/**
 * AuthController handles login, token refresh, and user info retrieval endpoints.
 * All routes are prefixed with /v1/auth.
 */
@Controller('v1/auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  /**
   * POST /v1/auth/login
   * Handles user login by validating credentials and issuing tokens.
   * Returns authentication tokens upon successful login.
   */
  @Post('login')
  @HttpCode(201)
  async login(
    @Body()
    dto: LoginDto,
  ): Promise<AuthViewZod> {
    // Extract identifier from provided fields (identifier, username, or email)
    const identifier = dto.identifier ?? dto.username ?? dto.email;
    if (!identifier) throw new BadRequestException('identifier/username/email required');

    // Ensure password is provided and not empty
    if (!dto.password || dto.password.trim() === '') {
      throw new BadRequestException('password required');
    }

    // Validate user credentials
    const user = await this.auth.validateUser(identifier, dto.password);

    // Issue and return authentication tokens for the validated user
    return await this.auth.issueTokens(user);
  }

  /**
   * POST /v1/auth/refresh
   * Protected endpoint to refresh authentication tokens using a valid refresh token.
   * Requires RefreshJwtAuthGuard to validate the refresh token.
   */
  @Post('refresh')
  @UseGuards(RefreshJwtAuthGuard)
  async refresh(
    @Req()
    req: Request & {
      user: {
        sub: string;
        pns: string;
        username: string;
        email?: string;
        role?: string;
      };
    },
  ): Promise<AuthViewZod> {
    // Issue new authentication tokens based on the validated refresh token's user info
    return this.auth.issueTokens(req.user);
  }

  /**
   * GET /v1/auth/me
   * Protected endpoint to retrieve information about the currently authenticated user.
   * Requires JwtAuthGuard to validate the access token.
   */
  @Get('me')
  @UseGuards(JwtAuthGuard)
  me(
    @Req()
    req: Request & {
      user?: { username?: string; pns?: string; role?: string[] };
    },
  ): MeViewZod {
    // Extract user payload from request, defaulting to empty object if undefined
    const payload = req.user ?? {};

    // Use Zod schema to validate and parse user info before returning
    const schema = MeViewZ as unknown as ZodType<MeViewZod>;
    return schema.parse({
      username: payload.username ?? '',
      pns: payload.pns ?? '',
      role: payload.role ?? [],
    });
  }
}
