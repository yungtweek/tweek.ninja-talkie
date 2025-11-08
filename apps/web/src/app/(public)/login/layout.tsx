'use client';
import React, { ReactNode } from 'react';
import { clsx } from 'clsx';
import styles from '@/app/(app)/page.module.scss';
import Header from '@/components/Header';

export default function LoginLayout({ children }: { children: ReactNode }) {
  return (
    <div className={clsx(styles.wrapper)}>
      <Header />
      <main>{children}</main>
    </div>
  );
}
