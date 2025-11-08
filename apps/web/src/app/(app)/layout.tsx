'use client';
import React, { ReactNode, useEffect, useState, useRef } from 'react';
import { usePathname } from 'next/navigation';

import { useAuthBootstrap } from '@/features/auth/useAuthBootstrap';
import styles from '@/app/(app)/page.module.scss';
import Header from '@/components/Header';
import { clsx } from 'clsx';
import { useAuthState } from '@/features/auth/auth.store';
import ApolloProvider from '@/providers/ApolloProvider';

export default function TalkieLayout({
  children,
  sidebar,
}: {
  children: ReactNode;
  sidebar: ReactNode;
}) {
  useAuthBootstrap();
  const { user } = useAuthState();
  const pathname = usePathname();
  const isHome = pathname === '/';

  const [isSidebarOpen, setIsSidebarOpen] = useState(!isHome || !!user);
  const prevUserRef = useRef(!!user);

  useEffect(() => {
    prevUserRef.current = !!user;
    setIsSidebarOpen(!isHome || !!user);
  }, [user, isHome]);

  return (
    <ApolloProvider>
      <div
        className={clsx(styles.wrapper, isSidebarOpen ? styles.sidebarOpen : styles.noSidebar)}
        style={{ ['--aside-width' as any]: isSidebarOpen ? '240px' : '0px' }}
      >
        {/* Landmark: Skip to main content for keyboard/AT users */}
        <a href="#main" className={styles.skipLink}>
          Skip to content
        </a>
        {/* Site-wide header (global navigation/branding) */}
        <Header />
        <div className={styles.container}>
          <aside className={clsx(styles.aside, styles.wrap)} aria-hidden={!user}>
            {/* Landmark: Sidebar navigation for sessions */}
            <nav aria-label="Session navigation">{sidebar}</nav>
          </aside>
          {/* Landmark: Main content area (page-level) */}
          <main id="main" className={clsx(styles.main, styles.wrap)}>
            {children}
          </main>
        </div>
      </div>
    </ApolloProvider>
  );
}
