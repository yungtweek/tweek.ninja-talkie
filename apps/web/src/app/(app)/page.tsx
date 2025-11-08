'use client';
import styles from './page.module.scss';
import { useEffect } from 'react';
import Link from 'next/link';
import { chatStore } from '@/features/chat/chat.store';
import { useSessionsActions } from '@/features/chat/chat.sessions.store';
import { useAuthState } from '@/features/auth/auth.store';

export default function TalkieEntry() {
  const { reset } = chatStore();
  const { setSelectedSessionId, setActiveSessionId } = useSessionsActions();
  const { user } = useAuthState();
  useEffect(() => {
    setSelectedSessionId(null);
    setActiveSessionId(null);
    reset();
  }, [setActiveSessionId, setSelectedSessionId, reset]);

  return (
    <div className={styles.wrapper}>
      <main className={styles.hero__main}>
        <section className={styles.hero__intro}>
          <h1>
            Hi, I’m <span className="">TALKIE</span>😎
          </h1>
          <p className={styles.description}>
            An AI chat assistant built for real-time reasoning, streaming, and observability.
          </p>
        </section>

        <section className={styles.features}>
          <h2 className={styles.title}>Features</h2>
          <div className={styles.grid}>
            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>💬 Generative Chat</h3>
              <p className={styles.featureDesc}>
                Real-time text streaming powered by FastAPI and Kafka. Optimized for responsiveness
                and scalability.
              </p>
              <Link href={user ? '/chat' : '/login'} className={styles.cta}>
                {user ? 'Try your chat' : 'Login to test with demo chat'}
              </Link>
            </article>

            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>📄 RAG Search</h3>
              <p className={styles.featureDesc}>
                Retrieve and reason with your uploaded data using Weaviate and LangChain.
              </p>
              <Link href={user ? '/documents' : '/login'} className={styles.cta}>
                {user ? 'Try your data' : 'Login to test with demo data'}
              </Link>
            </article>

            <article className={styles.featureCard}>
              <h3 className={styles.featureTitle}>📊 Metrics Dashboard</h3>
              <p className={styles.featureDesc}>
                Observe latency, token usage, and performance through Prometheus & Grafana.
              </p>
              <Link
                href="/"
                className={styles.cta}
                style={{ cursor: 'not-allowed' }}
                onClick={e => e.preventDefault()}
              >
                🚧 Working on it...
              </Link>
            </article>
          </div>
        </section>
      </main>
    </div>
  );
}
