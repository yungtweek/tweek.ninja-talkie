// apps/web/src/middleware.ts
import { NextResponse, type NextRequest } from 'next/server';

const EXCLUDE_EXACT = new Set([
  '/api/auth/login',
  '/api/auth/refresh',
  '/api/auth/logout',
  '/api/auth/me',
  '/actions/auth/login',
]);
const EXCLUDE_PREFIX = ['/api/auth/public']; // extend as needed

// clear cookie key boundaries for safe splitting
const COOKIE_KEYS = ['access_token', 'refresh_token', 'last_refreshed_at'] as const;

const AUTH_CHECK_TTL_MS = 20_000; // skip re-check within 20 seconds

function isAuthTarget(path: string) {
  return (
    path.startsWith('/actions') ||
    path.startsWith('/documents') ||
    path.startsWith('/chat') ||
    path.startsWith('/api') ||
    path.startsWith('/gql')
  );
}

export async function middleware(req: NextRequest) {
  // console.debug('=> Middleware');
  // console.debug(`[Middleware] ${req.method} ${req.url}`);
  const url = req.nextUrl;
  const path = url.pathname;

  // request id + header base (used in all return paths)
  const rid = req.headers.get('x-request-id') ?? crypto.randomUUID();
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set('x-request-id', rid);
  // 1) Let CORS preflight pass
  if (req.method === 'OPTIONS') {
    const res = NextResponse.next({ request: { headers: requestHeaders } });
    res.headers.set('x-request-id', rid);
    return res;
  }

  // 2) Promote/remove Authorization header (exclusions first)
  const isExcluded = EXCLUDE_EXACT.has(path) || EXCLUDE_PREFIX.some(p => path.startsWith(p));
  if (isExcluded) {
    requestHeaders.delete('authorization');
  } else if (!req.headers.get('authorization')) {
    const token = req.cookies.get('access_token')?.value;
    if (token) requestHeaders.set('authorization', `Bearer ${token}`);
  }

  // 3) Unified Auth Guard (pages + APIs + SSE)
  if (isAuthTarget(path) && !isExcluded) {
    const now = Date.now();
    // Compute last auth/refresh timestamp using the most recent one
    const cookieTs = (name: string) => Number(req.cookies.get(name)?.value) || 0;
    const lastAuthActivity = Math.max(cookieTs('auth_checked_at'), cookieTs('last_refreshed_at'));
    if (now - lastAuthActivity < AUTH_CHECK_TTL_MS) {
      const res = NextResponse.next({ request: { headers: requestHeaders } });
      res.cookies.set('auth_checked_at', String(now), {
        httpOnly: true,
        sameSite: 'lax',
        path: '/',
        expires: new Date(now + AUTH_CHECK_TTL_MS),
        maxAge: Math.ceil(AUTH_CHECK_TTL_MS / 1000),
      });
      res.headers.set('x-request-id', rid);
      return res;
    }

    const cookie = req.headers.get('cookie') ?? '';
    const origin = url.origin;

    // Session check
    const me = await fetch(new URL('/api/auth/me', origin), {
      headers: { cookie },
      cache: 'no-store',
    });
    if (me.ok) {
      const res = NextResponse.next({ request: { headers: requestHeaders } });
      res.cookies.set('auth_checked_at', String(now), {
        httpOnly: true,
        sameSite: 'lax',
        path: '/',
        expires: new Date(now + AUTH_CHECK_TTL_MS),
        maxAge: Math.ceil(AUTH_CHECK_TTL_MS / 1000),
      });
      res.headers.set('x-request-id', rid);
      return res;
    }

    // Refresh
    const rr = await fetch(new URL('/api/auth/refresh', origin), {
      method: 'POST',
      headers: { cookie },
      cache: 'no-store',
    });
    if (!rr.ok) {
      url.pathname = '/login';
      return NextResponse.redirect(url);
    }

    // forward Set-Cookie from refresh + set TTL cookie
    const res = NextResponse.next({ request: { headers: requestHeaders } });
    const rawSetCookie = rr.headers.get('set-cookie');
    if (rawSetCookie) {
      // rr may coalesce multiple Set-Cookie values into a single string.
      // safely split using the explicit key list (COOKIE_KEYS)
      const boundaryRe = new RegExp(`(?=(?:${COOKIE_KEYS.join('|')})=)`, 'g');
      const setCookieList = rawSetCookie.split(boundaryRe).filter(Boolean);
      for (const c of setCookieList) {
        // Parse "name=value; Attr1=...; Attr2; ..."
        const parts = c.split(';').map(s => s.trim());
        const [nameValue, ...attrParts] = parts;
        const eqIdx = nameValue.indexOf('=');
        if (eqIdx <= 0) continue;
        const name = nameValue.slice(0, eqIdx);
        const value = nameValue.slice(eqIdx + 1);

        // Build cookie options understood by NextResponse.cookies.set
        const opts: {
          httpOnly?: boolean;
          secure?: boolean;
          sameSite?: 'lax' | 'strict' | 'none';
          path?: string;
          domain?: string;
          maxAge?: number;
          expires?: Date;
        } = {};

        for (const ap of attrParts) {
          const [kRaw, ...vParts] = ap.split('=');
          const k = kRaw.trim().toLowerCase();
          const v = vParts.join('=').trim();

          switch (k) {
            case 'httponly':
              opts.httpOnly = true;
              break;
            case 'secure':
              opts.secure = true;
              break;
            case 'samesite':
              // Normalize casing
              if (v) {
                const vv = v.toLowerCase();
                opts.sameSite = vv === 'strict' ? 'strict' : vv === 'none' ? 'none' : 'lax';
              }
              break;
            case 'path':
              opts.path = v || '/';
              break;
            case 'domain':
              opts.domain = v;
              break;
            case 'max-age':
              if (v) opts.maxAge = Number(v);
              break;
            case 'expires':
              if (v) opts.expires = new Date(v);
              break;
            default:
              // ignore unknown attributes
              break;
          }
        }

        // Set into NextResponse cookie store (safe with later res.cookies.set calls)
        res.cookies.set({ name, value, ...opts });
      }
    }
    // TTL cookie to avoid duplicate checks right after refresh
    res.cookies.set('auth_checked_at', String(now), {
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      expires: new Date(now + AUTH_CHECK_TTL_MS),
      maxAge: Math.ceil(AUTH_CHECK_TTL_MS / 1000),
    });
    res.headers.set('x-refreshed', '1');
    res.headers.set('x-request-id', rid);
    return res;
  }

  const res = NextResponse.next({ request: { headers: requestHeaders } });
  res.headers.set('x-request-id', rid);
  return res;
}

export const config = {
  matcher: ['/api/:path*', '/gql/:path*', '/documents/:path*', '/chat/:path*', '/actions/:path*'],
  // matcher: ['/api/:path*', '/gql/:path*', '/chat/:path*'],
};
