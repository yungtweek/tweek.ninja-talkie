'use server';

import { cookies, headers } from 'next/headers';
import { MeViewZ, MeViewZod } from '@talkie/types-zod';
import { ActionState } from '@/actions/actions.type';
import { ok, fail } from '@/actions/actions.type';

export async function meAction(): Promise<ActionState<MeViewZod, { status: number }>> {
  const rawCookie = (await cookies()).toString();
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/auth/me`, {
    method: 'GET',
    headers: {
      'content-type': 'application/json',
      'x-forwarded-user-agent': (await headers()).get('user-agent') ?? '',
      Cookie: rawCookie,
    },
    cache: 'no-store',
  });

  if (!res.ok) {
    return fail(`${res.statusText}` || `unauthorized`, {
      code: 'HTTP_ERROR',
      meta: { status: res.status },
    });
  }

  const json: unknown = await res.json();
  const me = MeViewZ.safeParse(json);

  if (!me.success) {
    return fail('Invalid response format', {
      code: 'BAD_RESPONSE',
      meta: { status: res.status },
    });
  }

  return ok(me.data, { status: res.status });
}
