// --- Apollo cache helpers -----------------------------------------------------
import { ChatSessionMetaFragment, ChatSessionMetaFragmentDoc } from '@/gql/graphql';
import { ApolloCache, type Reference } from '@apollo/client';

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
        const edge = {
          __typename: 'ChatSessionEdge',
          cursor: session.id,
          node: nodeRef,
        };
        if (!existing) {
          return {
            __typename: 'ChatSessionConnection',
            edges: [edge],
            pageInfo: {
              __typename: 'PageInfo',
              hasPreviousPage: false,
              hasNextPage: false,
              startCursor: session.id,
              endCursor: session.id,
            },
          };
        }
        const edges = Array.isArray(existing.edges) ? existing.edges.slice() : [];
        const already = nodeRef
          ? edges.some((e: any) => e?.node?.__ref === (nodeRef as any).__ref)
          : false;
        const nextEdges = nodeRef ? (already ? edges : [edge, ...edges]) : edges;
        const startCursor = nextEdges.length ? nextEdges[0].cursor : null;
        const endCursor = nextEdges.length ? nextEdges[nextEdges.length - 1].cursor : null;
        return {
          __typename: 'ChatSessionConnection',
          edges: nextEdges,
          pageInfo: {
            __typename: 'PageInfo',
            hasPreviousPage: false,
            hasNextPage: existing.pageInfo?.hasNextPage ?? false,
            startCursor,
            endCursor,
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
