// hooks/useAuthBootstrap.ts
'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/features/auth/useAuth';

export function useAuthBootstrap() {
  const { hydrate } = useAuth();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void (async () => {
      await hydrate();
      setReady(true);
    })();
  }, [hydrate]);

  return { ready };
}
