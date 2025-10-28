/**
 * Refresh JWT Strategy for NestJS Passport authentication.
 * Handles validation of long-lived refresh tokens.
 * Uses cookie and header extractors to support both HTTP and WebSocket contexts.
 */
import { Injectable } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, JwtFromRequestFunction, Strategy } from 'passport-jwt';
import type { JwtPayload } from './types/jwt-payload';
import { ConfigService } from '@nestjs/config';
import { extractWTokenFromCookieForWs } from '@/common/utils/cookie.util';

/**
 * Extract refresh token from cookies.
 * Specifically looks for `refresh_token` field.
 * @param req Express or WebSocket request object.
 * @returns string | null
 */
function extractTokenFromCookie(req: unknown): string | null {
  if (!req || typeof req !== 'object') return null;
  const r = req as { cookies?: Record<string, unknown> };
  const v = r.cookies?.refresh_token;
  return typeof v === 'string' ? v : null;
}

/**
 * Composite extractor combining multiple sources:
 * 1. WebSocket cookies via `extractWTokenFromCookieForWs`
 * 2. HTTP cookies via `extractTokenFromCookie`
 * 3. Authorization header (Bearer token)
 */
const compositeExtractor: JwtFromRequestFunction = ExtractJwt.fromExtractors([
  extractWTokenFromCookieForWs,
  extractTokenFromCookie,
  ExtractJwt.fromAuthHeaderAsBearerToken(),
]);

/**
 * Passport strategy for verifying refresh JWTs.
 * Uses a dedicated secret and audience different from access tokens.
 */
@Injectable()
export class RefreshJwtStrategy extends PassportStrategy(Strategy, 'jwt-refresh') {
  constructor(cfg: ConfigService) {
    super({
      jwtFromRequest: compositeExtractor,
      ignoreExpiration: false,
      // ⚠️ 여기서만 리프레시 시크릿/오디언스 사용
      secretOrKey: cfg.get<string>('REFRESH_JWT_SECRET')!,
      issuer: cfg.get<string>('JWT_ISSUER') ?? 'tweek.ninja',
      audience: cfg.get<string>('JWT_AUDIENCE') ?? 'talkie.users',
    });
  }

  /**
   * Validate and map JWT payload to attach minimal user info to request.
   * Optionally extend to verify version, jti, or blacklist state.
   */
  validate(payload: JwtPayload) {
    // (옵션) ver/jti, 세션 상태, 블랙리스트 확인 지점
    return {
      username: payload.username,
      sub: payload.sub,
      pns: payload.pns,
      email: payload.email,
      role: payload.role ?? 'user',
    };
  }
}
