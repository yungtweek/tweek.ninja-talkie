'use client';
import { useActionState, useCallback, useEffect } from 'react';
import { useAuthActions, useAuthState } from '@/features/auth/auth.store';
import { loginAction } from '@/actions/auth/login.action';
import { logoutAction } from '@/actions/auth/logout.action';
import { MeViewZod } from '@talkie/types-zod';
import { meAction } from '@/actions/auth/me.action';
import { ActionState, isSuccess } from '@/actions/actions.type';

// We now hit the REST route /api/auth/me instead of using the Server Action meAction
async function fetchMe(): Promise<{ ok: boolean; data?: any }> {
  try {
    const res = await fetch('/api/auth/me', {
      method: 'GET',
      headers: { accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json()) as MeViewZod;
    return { ok: true, data };
  } catch {
    return { ok: false };
  }
}

export function useAuth() {
  const { user, loading, error } = useAuthState();
  const { setUser, setLoading, setError, reset } = useAuthActions();
  const initial: ActionState<null, { nonce: string; status?: number }> = {
    success: false,
    data: null,
    error: { message: '' },
    meta: { nonce: '' },
  };
  const [state, login, isPending] = useActionState<
    ActionState<null, { nonce: string; status?: number }>,
    FormData
  >(loginAction, initial);

  useEffect(() => {
    // Ignore initial render before loginAction writes a nonce
    if (!state.meta?.nonce) return;

    if (!state.success) {
      setError(state.error?.message || 'Failed to login');
      return;
    }
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(undefined);
      try {
        const me = await meAction();
        if (!isSuccess(me)) {
          setUser(null);
          return Promise.reject(new Error(me.error?.message ?? 'login failed'));
        }
        if (!cancelled) {
          setError(undefined);
          reset();
        }
        setUser(me.data);
      } catch {
        if (!cancelled) {
          setError('Failed to get user info. Please login again.');
          reset();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.success, reset, setError, setLoading, setUser, state.meta?.nonce]);

  const logout = useCallback(async () => {
    try {
      await logoutAction();
    } finally {
      reset();
    }
  }, [reset]);

  const hydrate = useCallback(async () => {
    if (user) return; // 이미 유저 있으면 스킵
    setLoading(true);
    setError(undefined);
    try {
      const me = await fetchMe();
      const you = me.data as MeViewZod;
      if (!me.ok || !you) {
        setUser(null);
      } else {
        setUser(you);
      }
    } catch {
      setError('Failed to get user info. Please login again.');
      reset();
    } finally {
      setLoading(false);
    }
  }, [reset, setError, setLoading, setUser]);

  return { user, loading, error, logout, hydrate, reset, login, isPending };
}
