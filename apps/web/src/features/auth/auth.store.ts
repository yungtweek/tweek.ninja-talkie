// apps/web/src/store/auth.store.ts
'use client';
import { create } from 'zustand';
import type { MeViewZod } from '@talkie/types-zod';
import { useShallow } from 'zustand/react/shallow';

export type AuthState = {
  user: MeViewZod | null;
  loading: boolean;
  error?: string;
  // setters (동기)
  setUser: (u: MeViewZod | null) => void;
  setLoading: (v: boolean) => void;
  setError: (msg?: string) => void;
  reset: () => void;
};

export const authStore = create<AuthState>(set => ({
  user: null,
  loading: true,
  error: undefined,
  setUser: u => set({ user: u }),
  setLoading: v => set({ loading: v }),
  setError: msg => set({ error: msg }),
  reset: () => set({ user: null, loading: false, error: undefined }),
}));

export const useAuthState = () => {
  const user = authStore(s => s.user);
  const loading = authStore(s => s.loading);
  const error = authStore(s => s.error);
  return { user, loading, error };
};

export const useAuthActions = () =>
  authStore(
    useShallow(s => ({
      setUser: s.setUser,
      setLoading: s.setLoading,
      setError: s.setError,
      reset: s.reset,
    })),
  );
