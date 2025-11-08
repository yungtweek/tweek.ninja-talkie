'use client';
import { ApolloProvider as BaseApolloProvider } from '@apollo/client/react';
import { apolloClient } from '@/lib/apollo/apollo.client';
import type { ReactNode } from 'react';

export function ApolloProvider({ children }: { children: ReactNode }) {
  return <BaseApolloProvider client={apolloClient}>{children}</BaseApolloProvider>;
}

export default ApolloProvider;
