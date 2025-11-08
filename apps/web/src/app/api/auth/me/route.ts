// apps/web/src/app/api/auth/me/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { withBearer } from '@/features/auth/auth.util';
import { authChecker } from '@/features/auth/authChecker';
import { MeViewZ } from '@talkie/types-zod';

// Proxy to Nest `/auth/me` and return the body as-is.
// Requires that the access token is stored as an httpOnly cookie named `access_token`.
export async function GET(nextRequest: NextRequest) {
  if (!authChecker(nextRequest)) {
    return new NextResponse(null, { status: 204 });
  }

  const headers = await withBearer(nextRequest.headers, 'access');

  if (!headers.get('authorization')) {
    return NextResponse.json(
      { error: { message: 'Unauthorized', path: `${nextRequest.nextUrl.pathname}` } },
      { status: 401 },
    );
  }

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/auth/me`, {
    method: 'GET',
    headers: headers,
    credentials: 'include',
    cache: 'no-store',
  });

  const json = (await res.json()) as unknown;
  const validatedResponse = MeViewZ.safeParse(json);

  if (!validatedResponse.success) {
    return NextResponse.json({ error: { message: 'INVALID_RESPONSE' } }, { status: 500 });
  }

  return NextResponse.json(validatedResponse.data, { status: res.status });
}
