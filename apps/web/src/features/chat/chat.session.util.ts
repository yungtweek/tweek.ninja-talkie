// --- Apollo cache helpers -----------------------------------------------------
import { ChatSessionMetaFragment, ChatSessionMetaFragmentDoc } from '@/gql/graphql';
import { ApolloCache, type Reference } from '@apollo/client';

const toCursor = (value: string) => {
  if (typeof window !== 'undefined' && typeof window.btoa === 'function') {
    return window.btoa(value);
  }
  if (typeof globalThis !== 'undefined' && typeof globalThis.btoa === 'function') {
    return globalThis.btoa(value);
  }
  const buffer = (globalThis as {
    Buffer?: { from: (value: string, encoding: string) => { toString: (enc: string) => string } };
  }).Buffer;
  return buffer ? buffer.from(value, 'utf8').toString('base64') : value;
};

const sessionToCursor = (session: ChatSessionMetaFragment) => {
  const ts = session.updatedAt ?? session.createdAt ?? new Date().toISOString();
  return toCursor(`${ts}|${session.id}`);
};

export const writeSessionMeta = (cache: ApolloCache, session: ChatSessionMetaFragment) => {
  const cacheId = cache.identify({ __typename: 'ChatSession', id: session.id });
  cache.writeFragment<ChatSessionMetaFragment>({
    id: cacheId,
    fragment: ChatSessionMetaFragmentDoc,
    data: {
      __typename: 'ChatSession',
      id: session.id,
      title: session.title ?? null,
      createdAt: session.createdAt ?? new Date().toISOString(),
      updatedAt: session.updatedAt ?? new Date().toISOString(),
    },
  });
};

export const modifySessionMeta = (cache: ApolloCache, session: ChatSessionMetaFragment) => {
  cache.modify({
    fields: {
      chatSessionList(existing: any) {
        const nodeId = cache.identify({
          __typename: 'ChatSession',
          id: session.id,
        });
        const nodeRef: Reference | null = nodeId ? ({ __ref: nodeId } as Reference) : null;
        if (!nodeRef) return existing;
        const cursor = sessionToCursor(session);
        if (!existing) {
          const edge = {
            __typename: 'ChatSessionEdge',
            cursor,
            node: nodeRef,
          };
          return {
            __typename: 'ChatSessionConnection',
            edges: [edge],
            pageInfo: {
              __typename: 'PageInfo',
              hasPreviousPage: false,
              hasNextPage: false,
              startCursor: cursor,
              endCursor: cursor,
            },
          };
        }
        const edges = Array.isArray(existing.edges) ? existing.edges.slice() : [];
        const refKey = (nodeRef as any).__ref;
        const idx = edges.findIndex((e: any) => e?.node?.__ref === refKey);
        const existingCursor = idx >= 0 ? edges[idx]?.cursor ?? null : null;
        const filtered = edges.filter((e: any) => e?.node?.__ref !== refKey);
        const edge = {
          __typename: 'ChatSessionEdge',
          cursor: existingCursor ?? cursor,
          node: nodeRef,
        };
        const nextEdges = [edge, ...filtered];
        const prevPageInfo = existing.pageInfo ?? {};
        const startCursor = nextEdges.length ? nextEdges[0]?.cursor ?? null : null;
        const endCursor = nextEdges.length
          ? nextEdges[nextEdges.length - 1]?.cursor ?? null
          : null;
        return {
          __typename: 'ChatSessionConnection',
          edges: nextEdges,
          pageInfo: {
            __typename: 'PageInfo',
            hasPreviousPage: prevPageInfo.hasPreviousPage ?? false,
            hasNextPage: prevPageInfo.hasNextPage ?? false,
            startCursor: startCursor ?? prevPageInfo.startCursor ?? null,
            endCursor: endCursor ?? prevPageInfo.endCursor ?? null,
          },
        };
      },
    },
  });
};

type SessionHandlers = {
  onCreated: (s: ChatSessionMetaFragment) => void;
  onUpdated: (s: Partial<ChatSessionMetaFragment>) => void;
  onError?: (e: Event) => void;
};

export function openSessionEvents(jobId: string, handlers: SessionHandlers) {
  const es = new EventSource(`/api/session/events/${jobId}`, { withCredentials: true });

  es.addEventListener(
    'CREATED',
    e => {
      const p = JSON.parse(e.data as string) as { session?: ChatSessionMetaFragment };
      if (p.session) handlers.onCreated(p.session);
    },
    { once: true },
  );

  es.addEventListener(
    'UPDATED',
    e => {
      const p = JSON.parse(e.data as string) as { session?: Partial<ChatSessionMetaFragment> };
      if (p.session) handlers.onUpdated?.(p.session);
      es.close();
    },
    { once: true },
  );

  es.addEventListener(
    'error',
    e => {
      handlers.onError?.(e);
      es.close();
    },
    { once: true },
  );

  return { close: () => es.close() };
}
