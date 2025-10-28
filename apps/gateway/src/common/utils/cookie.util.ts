/**
 * Parse raw cookie string into a key-value map.
 * @param raw raw cookie header string
 * @returns Record of cookie key-value pairs
 */
export function parseCookie(raw?: unknown): Record<string, string> {
  if (typeof raw !== 'string' || raw.length === 0) return {};
  const out: Record<string, string> = {};
  for (const part of raw.split(';')) {
    const [k, ...rest] = part.trim().split('=');
    if (!k) continue;
    out[k] = decodeURIComponent(rest.join('=') ?? '');
  }
  return out;
}

/**
 * Extract JWT access token from WebSocket handshake cookies.
 * Supports multiple fallback paths within socket.extra and headers.
 * Used when authenticating via GraphQL subscriptions or WebSocket clients.
 */
export function extractWTokenFromCookieForWs(req: unknown): string | null {
  if (!req || typeof req !== 'object') return null;

  const r = req as Record<string, unknown> | null | undefined;

  // Safely access nested request properties using 'any' to bypass ESLint unsafe access warnings.
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment,@typescript-eslint/no-unsafe-member-access
  const extra = (r as any)?.extra;
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment,@typescript-eslint/no-unsafe-member-access
  const hdrs = (r as any)?.headers;

  const rawCookie: unknown =
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    extra?.request?.headers?.cookie ??
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    extra?.socket?.request?.headers?.cookie ??
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    hdrs?.cookie ??
    null;

  // Avoid logging raw cookies or tokens for security reasons.

  const ck = parseCookie(rawCookie);
  const t = ck['access_token'] ?? ck['AT'] ?? ck['Authorization'] ?? ck['authorization'] ?? null;

  return t !== null && t.length > 0 ? t : null;
}
