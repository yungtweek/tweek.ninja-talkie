// app/api/auth/refresh/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { withAuthCookies, withBearer } from '@/features/auth/auth.util';
import { AuthViewZ } from '@talkie/types-zod';

export async function POST(nextRequest: NextRequest) {
  const headers = await withBearer(nextRequest.headers, 'refresh');

  // 🔒 Guard: if Authorization is absent, return 401 here instead of letting apiFetch throw
  const h = new Headers(headers);
  if (!h.get('authorization')) {
    return NextResponse.json(
      {
        items: [],
        error: { status: 401, message: 'Unauthorized', path: '/chat' },
        timestamp: new Date().toISOString(),
      },
      { status: 401 },
    );
  }

  h.set('Content-Type', 'application/json');
  const nestBase = process.env.NEXT_PUBLIC_API_BASE_URL!;
  const upstreamResponse = await fetch(`${nestBase}/v1/auth/refresh`, {
    method: 'POST',
    headers: h,
    cache: 'no-store',
  });

  if (!upstreamResponse.ok) {
    return NextResponse.json({ error: 'refresh failed' }, { status: upstreamResponse.status });
  }
  const rawResponse: unknown = await upstreamResponse.json();
  const validatedResponse = AuthViewZ.safeParse(rawResponse);
  if (!validatedResponse.success) {
    return NextResponse.json({ error: 'INVALID_RESPONSE' }, { status: 500 });
  }
  return withAuthCookies(validatedResponse.data, { status: upstreamResponse.status });
}
