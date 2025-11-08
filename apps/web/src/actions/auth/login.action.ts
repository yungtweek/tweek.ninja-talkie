'use server';
import { headers } from 'next/headers';
import { AuthViewZ } from '@talkie/types-zod';
import { setAuthCookies } from '@/features/auth/auth.util';
import { ActionState, ok, fail } from '@/actions/actions.type';

export async function loginAction(
  _prev: ActionState<null, { nonce: string }>,
  formData: FormData,
): Promise<ActionState<null, { nonce: string; status?: number }>> {
  const rawEmail = formData.get('email');
  const email = typeof rawEmail === 'string' ? rawEmail : '';

  const rawPassword = formData.get('password');
  const password = typeof rawPassword === 'string' ? rawPassword : '';

  const nonce = crypto.randomUUID();

  if (!email || !password)
    return fail('Missing credentials', { code: 'BAD_INPUT', meta: { nonce } });

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/auth/login`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-forwarded-user-agent': (await headers()).get('user-agent') ?? '',
    },
    body: JSON.stringify({ email, password }),
    cache: 'no-store',
  });

  // Special-case common auth errors for clearer UX and analytics
  if (res.status === 401) {
    const bodyText = await res.text().catch(() => '');
    return fail(bodyText || 'Invalid credentials', {
      code: 'UNAUTH',
      meta: { nonce, status: res.status },
    });
  }

  if (res.status === 429) {
    const bodyText = await res.text().catch(() => '');
    return fail(bodyText || 'Too many attempts, please try again later', {
      code: 'RATE_LIMIT',
      meta: { nonce, status: res.status },
    });
  }

  if (res.status >= 500 && res.status <= 599) {
    const bodyText = await res.text().catch(() => '');
    return fail(bodyText || 'Auth service unavailable', {
      code: 'UPSTREAM',
      meta: { nonce, status: res.status },
    });
  }

  if (!res.ok) {
    const msg = await res.text().catch(() => 'Login failed');
    return fail(msg || 'Login failed', { code: 'HTTP_ERROR', meta: { nonce, status: res.status } });
  }

  const json: unknown = await res.json();
  const tokens = AuthViewZ.safeParse(json);

  if (!tokens.success) {
    return fail('Invalid response', { code: 'BAD_RESPONSE', meta: { nonce, status: 400 } });
  }

  await setAuthCookies(tokens.data);

  return ok(null, { nonce, status: res.status });
}
