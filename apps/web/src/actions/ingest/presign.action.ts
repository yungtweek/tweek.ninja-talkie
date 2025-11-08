'use server';

import {
  PresignRequest,
  PresignRequestZ,
  PresignResponse,
  PresignResponseZ,
} from '@talkie/types-zod';
import { cookies } from 'next/headers';
import { ActionState, ok, fail } from '@/actions/actions.type';

const URL = `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/ingest/presign/put`;
export async function presignAction(
  input: PresignRequest,
): Promise<ActionState<PresignResponse, { status: number }>> {
  const rawCookie = (await cookies()).toString();
  const validated = PresignRequestZ.safeParse(input);

  if (!validated.success) {
    return fail('Invalid request', { code: 'BAD_INPUT', meta: { status: 400 } });
  }
  const res = await fetch(URL, {
    method: 'POST',
    body: JSON.stringify(validated.data),
    headers: {
      'Content-Type': 'application/json',
      Cookie: rawCookie,
    },
  });

  if (!res.ok) {
    const msg = res.statusText || 'Upstream error';
    return fail(msg, { code: 'HTTP_ERROR', meta: { status: res.status } });
  }

  const rawResponse: unknown = await res.json();
  const validatedResponse = PresignResponseZ.safeParse(rawResponse);

  if (!validatedResponse.success) {
    return fail('Invalid response', { code: 'BAD_RESPONSE', meta: { status: res.status } });
  }

  return ok(validatedResponse.data, { status: res.status });
}
