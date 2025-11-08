import React, { ReactNode } from 'react';

import '@/app/globals.scss';

export default function TalkieLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
