// apps/web/src/lib/apollo.links.ts
import {
  ApolloLink,
  CombinedGraphQLErrors,
  CombinedProtocolErrors,
  HttpLink,
} from '@apollo/client';
import { ErrorLink } from '@apollo/client/link/error';
import { SetContextLink } from '@apollo/client/link/context';
import { Observable } from '@apollo/client';

let refreshing: Promise<boolean | null> | null = null;
const refreshToken = () => {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include',
          cache: 'no-store',
        });

        return res.ok ?? null;
      } catch {
        return null;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
};

export const authLink = new SetContextLink((_op: any, prev: any) => ({
  headers: { ...(prev?.headers ?? {}) },
}));

export const errorLink = new ErrorLink(({ error, operation, forward }) => {
  // 로깅 + UNAUTH 판단
  let isUnauth = false;
  if (CombinedGraphQLErrors.is(error)) {
    for (const { message, locations, path, extensions } of error.errors) {
      console.log(`[GraphQL error]: Message: ${message}, Location: ${locations}, Path: ${path}`);
      if (
        extensions?.code === 'UNAUTHENTICATED' ||
        String(message).toLowerCase().includes('unauth')
      ) {
        isUnauth = true;
      }
    }
  } else if (CombinedProtocolErrors.is(error)) {
    for (const { message, extensions } of error.errors) {
      console.log(
        `[Protocol error]: Message: ${message}, Extensions: ${JSON.stringify(extensions)}`,
      );
      const httpStatus = (extensions as any)?.http?.status;
      if (httpStatus === 401 || (extensions as any)?.code === 'UNAUTHENTICATED') {
        isUnauth = true;
      }
    }
  } else {
    console.error(`[Network error]:`, error);
    const status = (error as any)?.statusCode ?? (error as any)?.status;
    if (status === 401) isUnauth = true;
  }

  if (!isUnauth) {
    return;
  }

  if (!forward) {
    return new Observable<ApolloLink.Result>(observer => {
      observer.error(error as any);
    });
  }

  const { alreadyRetried } = (operation.getContext() as any) ?? {};
  if (alreadyRetried) return;

  operation.setContext({ alreadyRetried: true });

  // 리프레시 후 원요청 재시도
  return new Observable<ApolloLink.Result>(observer => {
    (async () => {
      const ok = await refreshToken();
      if (!ok) {
        observer.error(error as any);
        return;
      }

      const sub = forward(operation).subscribe({
        next: (v: ApolloLink.Result) => observer.next(v),
        error: e => observer.error(e),
        complete: () => observer.complete(),
      });

      return () => sub.unsubscribe();
    })().catch(e => observer.error(e));
  });
});

// 3) HttpLink (필요 시 credentials 포함)
export const httpLink = new HttpLink({
  uri: process.env.NEXT_PUBLIC_GQL_HTTP_URL!,
  credentials: 'include',
});

// 최종 링크 체인
export const link = ApolloLink.from([errorLink, authLink, httpLink]);
