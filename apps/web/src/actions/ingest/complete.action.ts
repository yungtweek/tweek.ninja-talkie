'use server';

import {
  CompleteRequest,
  CompleteRequestZ,
  CompleteResponse,
  CompleteResponseZ,
} from '@talkie/types-zod';
import { cookies } from 'next/headers';
import type { ActionState } from '@/actions/actions.type';
import { ok, fail } from '@/actions/actions.type';

export async function completeAction(
  input: CompleteRequest,
): Promise<ActionState<CompleteResponse>> {
  const rawCookie = (await cookies()).toString();
  const validated = CompleteRequestZ.safeParse(input);
  if (!validated.success) {
    return fail('Invalid request', { code: 'BAD_INPUT', meta: { status: 400 } });
  }
  const url = `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/ingest/complete`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Cookie: rawCookie,
    },
    body: JSON.stringify(validated.data),
  });

  if (!res.ok) {
    const msg = res.statusText || 'Upstream error';
    return fail(msg, { code: 'HTTP_ERROR', meta: { status: res.status } });
  }

  const rawResponse: unknown = await res.json();
  const validatedResponse = CompleteResponseZ.safeParse(rawResponse);

  if (!validatedResponse.success) {
    return fail('Invalid response', { code: 'BAD_RESPONSE', meta: { status: res.status } });
  }

  return ok(validatedResponse.data, { status: res.status });
}
