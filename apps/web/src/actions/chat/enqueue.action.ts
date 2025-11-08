'use server';

import { EnqueueInput, EnqueueInputZ, EnqueueOutput, EnqueueOutputZ } from '@talkie/types-zod';
import { cookies } from 'next/headers';
import { ActionState, ok, fail } from '@/actions/actions.type';

export async function enqueueAction(
  input: EnqueueInput,
): Promise<ActionState<EnqueueOutput, { status: number }>> {
  const rawCookie = (await cookies()).toString();
  const validated = EnqueueInputZ.safeParse(input);
  if (!validated.success) {
    return fail('Invalid request', { code: 'BAD_INPUT', meta: { status: 400 } });
  }
  const url = `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/chat`;
  const upstreamResponse = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Cookie: rawCookie,
    },
    body: JSON.stringify(validated.data),
  });

  if (!upstreamResponse.ok) {
    const msg = upstreamResponse.statusText || 'Upstream error';
    return fail(msg, { code: 'HTTP_ERROR', meta: { status: upstreamResponse.status } });
  }

  const rawResponse: unknown = await upstreamResponse.json();
  const validatedResponse = EnqueueOutputZ.safeParse(rawResponse);
  if (!validatedResponse.success) {
    return fail('Invalid response', {
      code: 'BAD_RESPONSE',
      meta: { status: upstreamResponse.status },
    });
  }

  return ok(validatedResponse.data, { status: upstreamResponse.status });
}
