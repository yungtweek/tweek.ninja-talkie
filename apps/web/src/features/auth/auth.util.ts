// lib/auth.util.ts
import { cookies, headers as nextHeaders } from 'next/headers';
import { NextResponse } from 'next/server';
import { AuthViewZod } from '@talkie/types-zod';

type BearerKind = 'access' | 'refresh' | 'auto';

export async function withBearer(
  init?: HeadersInit,
  kind: BearerKind = 'access',
): Promise<Headers> {
  const h = new Headers(init);

  if (h.has('authorization')) return h;

  const tokenArg = kind === 'refresh' ? 'refresh_token' : 'access_token';
  const tokenFromCookie = (await cookies()).get(tokenArg)?.value;
  if (tokenFromCookie) {
    h.set('authorization', `Bearer ${tokenFromCookie}`);
    return h;
  }

  const fwdAuth = (await nextHeaders()).get('authorization');
  if (fwdAuth) h.set('authorization', fwdAuth);
  return h;
}

function writeAuthCookiesToJar(
  jar: { set(name: string, value: string, options: any): void },
  tokens: AuthViewZod,
) {
  if (tokens?.access?.token) {
    jar.set('access_token', tokens.access.token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: tokens.access.expiresIn,
    });
  }

  if (tokens?.refresh?.token) {
    jar.set('refresh_token', tokens.refresh.token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: tokens.refresh.expiresIn,
    });
  }
  const AUTH_CHECK_TTL_MS = 20_000;
  const now = Date.now();
  jar.set('last_refreshed_at', String(now), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    expires: new Date(now + AUTH_CHECK_TTL_MS),
    maxAge: Math.ceil(AUTH_CHECK_TTL_MS / 1000),
  });
}

/**
 * Response helper for API/route handlers (and fetch proxy routes).
 *
 * Use this when you need to RETURN a NextResponse that also sets auth cookies.
 *
 * ✅ Route handlers (e.g. app/api/!*route.ts): OK
 * ✅ Server-side fetch proxy endpoints: OK
 * ❌ Server Actions: avoid returning NextResponse — prefer `await setAuthCookies(tokens)`
 *    and return a plain serializable object instead.
 *
 * @param data  Parsed auth view (access/refresh tokens + TTLs)
 * @param body  JSON body to return
 * @param status HTTP status code
 */
export function withAuthCookies<T>(data: AuthViewZod, body: T, status = 200) {
  const res = NextResponse.json(body, { status });

  writeAuthCookiesToJar(res.cookies, data);

  return res;
}

export async function setAuthCookies(data: AuthViewZod) {
  const jar = await cookies();
  writeAuthCookiesToJar(jar, data);
}
