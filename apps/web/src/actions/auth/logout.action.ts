'use server';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { ActionState, ok } from '@/actions/actions.type';

async function clearAuthCookies() {
  const jar = await cookies();
  jar.delete({ name: 'access_token', path: '/' });
  jar.delete({ name: 'refresh_token', path: '/' });
  jar.delete({ name: 'auth_checked_at', path: '/' });
  jar.delete({ name: 'last_refreshed_at', path: '/' });
}

export async function logoutAction(): Promise<never> {
  await clearAuthCookies();
  redirect('/');
}

export async function logoutActionSilent(): Promise<ActionState<null, { status?: number }>> {
  await clearAuthCookies();
  return ok(null, { status: 200 });
}
