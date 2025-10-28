// src/modules/auth/types/jwt-payload.ts
export interface JwtPayload {
  /**
   * Internal immutable identifier (UUID v4)
   * - Same as DB users.user_id
   * - Primary key for all internal references
   */
  sub: string;

  /**
   * Public Namespace (PNS)
   * - User's external public identifier
   * - One-to-one mapping with internal immutable user_id (sub)
   * - Used for identification in external systems or public APIs
   * - Not confidential information, a safe alternative key to avoid exposing internal UUID directly
   */
  pns: string;

  /**
   * Username for external exposure
   * - Used in URLs, profiles, etc.
   */
  username: string;

  /**
   * Email (optional)
   * - Additional information for authenticated accounts
   */
  email?: string;

  /**
   * Role (permission distinction)
   * - e.g. 'user' | 'admin' | 'system'
   */
  role?: string;

  /**
   * JWT issued at time (Unix seconds)
   * - Automatically generated (jsonwebtoken)
   */
  iat?: number;

  /**
   * JWT expiration time (Unix seconds)
   * - Automatically generated (jsonwebtoken)
   */
  exp?: number;

  /**
   * Token version (optional)
   * - Used to determine reissue on account suspension/logout
   */
  ver?: number;
}
