/**
 * AuthService
 * - Validates user credentials against the UsersRepository
 * - Issues access & refresh JWTs using separate JwtService instances
 * - Designed for portfolio/open-source readability (no secrets embedded)
 */
// src/modules/auth/auth.service.ts
import { Inject, Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import type { JwtPayload } from './types/jwt-payload';
import { UsersRepository } from '@/modules/users/users.repository';
import { AuthViewZ } from '@tweek/types-zod';
import type { AuthViewZod } from '@tweek/types-zod';

/** Service layer for authentication flows (login, token issuance). */
@Injectable()
export class AuthService {
  constructor(
    private readonly usersRepo: UsersRepository,
    private readonly jwt: JwtService,
    // Separate JwtService for refresh tokens allows different secrets/exp settings via DI token
    @Inject('REFRESH_JWT') private readonly rjwt: JwtService, // refresh
  ) {}

  /**
   * Validate user credentials and build a minimal JWT payload.
   * @param identifier username | email | custom identifier
   * @param password plaintext password (validated by repository)
   * @throws UnauthorizedException when credentials are invalid
   * @returns subset of JwtPayload fields (no role if not applicable)
   */
  async validateUser(identifier: string, password: string) {
    const user = await this.usersRepo.findByIdentifierAndPwd(identifier, password);
    if (!user) throw new UnauthorizedException('Invalid credentials');
    return {
      sub: user.id,
      pns: user.public_ns,
      username: user.username,
      email: user.email ?? undefined,
    };
  }

  /**
   * Issue both access & refresh tokens.
   * - Access token: short-lived (15 minutes default)
   * - Refresh token: longer-lived (14 days default)
   *
   * @param user Partial JwtPayload-like object (sub, pns, username, email?, role?)
   * @returns AuthViewZod (validated shape for API response)
   */
  async issueTokens(user: {
    sub: string;
    pns: string;
    username: string;
    email?: string;
    role?: string;
  }): Promise<AuthViewZod> {
    // JWT payload shared by both access and refresh tokens
    const payload: JwtPayload = {
      sub: user.sub,
      pns: user.pns,
      username: user.username,
      email: user.email,
      role: user.role,
    };
    const now = Math.floor(Date.now() / 1000); // current time in Unix seconds (UTC)
    // Token lifetimes (can be overridden by module configuration)
    const accessExp = now + 60 * 15; // 15min
    const refreshExp = now + 60 * 60 * 24 * 14; // 14days

    // Sign access token using the default JwtService instance
    const accessToken = await this.jwt.signAsync(payload, {
      expiresIn: accessExp - now,
    });
    // Sign refresh token using the dedicated refresh JwtService (different secret/exp)
    const refreshToken = await this.rjwt.signAsync(payload, {
      expiresIn: refreshExp - now,
    });

    // Normalize and validate response shape with Zod before returning to controller
    return AuthViewZ.parse({
      access: {
        tokenType: 'Bearer',
        token: accessToken,
        issuedAt: now,
        expiresIn: accessExp - now,
        expiresAt: accessExp,
      },
      refresh: {
        tokenType: 'Bearer',
        token: refreshToken,
        expiresIn: refreshExp - now,
        expiresAt: refreshExp,
      },
    });
  }
}
