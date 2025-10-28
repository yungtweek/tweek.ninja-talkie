// src/modules/auth/jwt.strategy.ts
/**
 * JWT Strategy for NestJS Passport authentication.
 * Supports token extraction from both HTTP cookies and WebSocket headers.
 * This strategy validates JWT payloads and attaches the decoded user to the request object.
 */
import { Injectable } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, JwtFromRequestFunction, Strategy } from 'passport-jwt';
import { ConfigService } from '@nestjs/config';
import type { JwtPayload } from './types/jwt-payload';
import { extractWTokenFromCookieForWs } from '@/common/utils/cookie.util';

/**
 * Extract JWT access token from standard HTTP cookies.
 * Looks for `access_token` cookie field.
 */
function extractTokenFromCookie(req: unknown): string | null {
  if (!req || typeof req !== 'object') return null;
  const r = req as { cookies?: Record<string, unknown> };
  const v = r.cookies?.access_token;
  return typeof v === 'string' ? v : null;
}

/**
 * Composite token extractor that checks, in order:
 * 1. WebSocket cookies (extractWTokenFromCookieForWs)
 * 2. HTTP cookies (extractTokenFromCookie)
 * 3. Authorization header (Bearer token)
 */
const compositeExtractor: JwtFromRequestFunction = ExtractJwt.fromExtractors([
  extractWTokenFromCookieForWs,
  extractTokenFromCookie,
  ExtractJwt.fromAuthHeaderAsBearerToken(),
]);

/**
 * Passport JWT Strategy using composite extractors.
 * Configures secret, issuer, and audience from environment variables.
 */
@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor(cfg: ConfigService) {
    super({
      jwtFromRequest: compositeExtractor,
      ignoreExpiration: false,
      secretOrKey: cfg.get<string>('JWT_SECRET')!,
      issuer: cfg.get<string>('JWT_ISSUER') ?? 'tweek.ninja',
      audience: cfg.get<string>('JWT_AUDIENCE') ?? 'talkie.users',
    });
  }

  /**
   * Validate and return user info to attach to request.user.
   * Can perform additional blacklist or user status checks here.
   */
  validate(payload: JwtPayload) {
    // 필요하다면 여기서 사용자 상태 체크/블랙리스트 확인 가능
    return {
      username: payload.username,
      sub: payload.sub,
      pns: payload.pns,
      email: payload.email,
      role: payload.role ?? 'user',
    };
  }
}
