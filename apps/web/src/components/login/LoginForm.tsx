'use client';
import { useEffect, useState } from 'react';
import styles from './LoginFrom.module.scss';
import { useAuth } from '@/features/auth/useAuth';
import { useRouter, usePathname } from 'next/navigation';

type Props = {
  onSuccessAction?: () => void;
  compact?: boolean;
  defaultEmail?: string;
};

export default function LoginForm({ onSuccessAction, compact, defaultEmail }: Props) {
  const { error, isPending, login, user, loading } = useAuth(); // login = formAction 별칭
  const router = useRouter();
  const pathname = usePathname();
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    if (!user) return undefined;
    setLocked(true);
    onSuccessAction?.();
    const delay = 500;

    const timeout = setTimeout(() => {
      router.replace('/');
    }, delay);

    return () => clearTimeout(timeout);
  }, [user, onSuccessAction, router, pathname]);

  const isAuthed = !!user;

  if (loading) {
    return (
      <section className={styles.loginSection}>
        <div className={styles.loginCard}>
          <div className={styles.spinnerWrapper}>
            <div className={styles.spinner}></div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.loginSection}>
      <div className={compact ? `${styles.loginCard} ${styles.compact}` : styles.loginCard}>
        {isAuthed ? (
          <div className={styles.success}>
            <h2 className={styles.title}>Signed in</h2>
            <p className={styles.successText}>Welcome back. Redirecting…</p>
          </div>
        ) : (
          <>
            <h2 className={styles.title}>Sign in</h2>
            <form
              action={login}
              className={styles.form}
              noValidate
              onSubmit={() => setLocked(true)}
            >
              {!isPending && !locked ? (
                <>
                  <label className={styles.label}>
                    <span>Email</span>
                    <input
                      name="email"
                      type="email"
                      defaultValue={defaultEmail}
                      required
                      autoComplete="email"
                      className={styles.input}
                    />
                  </label>
                  <label className={styles.label}>
                    <span>Password</span>
                    <input
                      name="password"
                      type="password"
                      required
                      autoComplete="current-password"
                      className={styles.input}
                    />
                  </label>
                </>
              ) : (
                <div className={styles.spinnerWrapper}>
                  <div className={styles.spinner}></div>
                </div>
              )}

              <button
                type="submit"
                disabled={isPending || locked}
                aria-busy={isPending || locked}
                className={styles.submit}
              >
                {isPending || locked ? 'Logging in…' : 'Log in'}
              </button>

              {error && (
                <p role="alert" className={styles.error}>
                  {error}
                </p>
              )}
            </form>
          </>
        )}
      </div>
    </section>
  );
}
