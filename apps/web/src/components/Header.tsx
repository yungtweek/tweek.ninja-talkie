'use client';
import { useEffect, useState } from 'react';
import styles from './Header.module.scss';

import { useAuthState } from '@/features/auth/auth.store';
import { useAuth } from '@/features/auth/useAuth';
import { useRouter, usePathname } from 'next/navigation';
import { useChatActions } from '@/features/chat/chat.store';
import Link from 'next/link';

export default function Header() {
  const { user, loading } = useAuthState();
  const { reset } = useChatActions();
  const { logout } = useAuth();

  const router = useRouter();
  const pathname = usePathname();

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const showLoading = !mounted || loading;

  return (
    <header className={styles.header}>
      <Link href="/">
        <h1>TALKIE 🤔</h1>
      </Link>
      <div>
        {showLoading ? (
          <button type="button" style={{ minWidth: '40px' }} disabled>
            ...
          </button>
        ) : user ? (
          <button
            type="button"
            onClick={() => {
              void (async () => {
                reset();
                await logout();
              })();
            }}
          >
            logout
          </button>
        ) : (
          pathname !== '/login' && (
            <button type="button" onClick={() => router.push('/login')}>
              login
            </button>
          )
        )}
      </div>
    </header>
  );
}
