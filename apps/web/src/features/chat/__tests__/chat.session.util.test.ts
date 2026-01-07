import { InMemoryCache, gql } from '@apollo/client';
import { type ChatSessionMetaFragment } from '@/gql/graphql';
import { modifySessionMeta, writeSessionMeta } from '@/features/chat/chat.session.util';

const ChatSessionListWithCursorDocument = gql`
  query ChatSessionListWithCursor($first: Int = 50) {
    chatSessionList(first: $first) {
      edges {
        cursor
        node {
          id
          title
          createdAt
          updatedAt
        }
      }
      pageInfo {
        hasPreviousPage
        hasNextPage
        startCursor
        endCursor
      }
    }
  }
`;

type Edge = {
  __typename: 'ChatSessionEdge';
  cursor: string;
  node: {
    __typename: 'ChatSession';
    id: string;
    title?: string | null;
    createdAt?: string | null;
    updatedAt?: string | null;
  };
};

const makeCache = () =>
  new InMemoryCache({
    typePolicies: {
      ChatSession: { keyFields: ['id'] },
    },
  });

const writeSessionList = (cache: InMemoryCache, edges: Edge[]) => {
  cache.writeQuery({
    query: ChatSessionListWithCursorDocument,
    variables: { first: 50 },
    data: {
      chatSessionList: {
        __typename: 'ChatSessionConnection',
        edges,
        pageInfo: {
          __typename: 'PageInfo',
          hasPreviousPage: false,
          hasNextPage: false,
          startCursor: edges[0]?.cursor ?? null,
          endCursor: edges[edges.length - 1]?.cursor ?? null,
        },
      },
    },
  });
};

describe('modifySessionMeta', () => {
  it('moves an existing session to the top without changing its cursor', () => {
    const cache = makeCache();
    const edges: Edge[] = [
      {
        __typename: 'ChatSessionEdge',
        cursor: 'cursor-a',
        node: {
          __typename: 'ChatSession',
          id: 'a',
          title: 'A',
          createdAt: '2024-01-01T00:00:00.000Z',
          updatedAt: '2024-01-01T00:00:00.000Z',
        },
      },
      {
        __typename: 'ChatSessionEdge',
        cursor: 'cursor-b',
        node: {
          __typename: 'ChatSession',
          id: 'b',
          title: 'B',
          createdAt: '2024-01-02T00:00:00.000Z',
          updatedAt: '2024-01-02T00:00:00.000Z',
        },
      },
    ];
    writeSessionList(cache, edges);

    const updated: ChatSessionMetaFragment = {
      __typename: 'ChatSession',
      id: 'b',
      title: 'B',
      createdAt: '2024-01-02T00:00:00.000Z',
      updatedAt: '2024-01-03T00:00:00.000Z',
    };

    writeSessionMeta(cache, updated);
    modifySessionMeta(cache, updated);

    const result = cache.readQuery({
      query: ChatSessionListWithCursorDocument,
      variables: { first: 50 },
    });

    expect(result?.chatSessionList.edges[0]?.node.id).toBe('b');
    expect(result?.chatSessionList.edges[0]?.cursor).toBe('cursor-b');
    expect(result?.chatSessionList.edges[1]?.node.id).toBe('a');
  });

  it('adds a new session to the top with a computed cursor', () => {
    const cache = makeCache();
    const edges: Edge[] = [
      {
        __typename: 'ChatSessionEdge',
        cursor: 'cursor-a',
        node: {
          __typename: 'ChatSession',
          id: 'a',
          title: 'A',
          createdAt: '2024-01-01T00:00:00.000Z',
          updatedAt: '2024-01-01T00:00:00.000Z',
        },
      },
    ];
    writeSessionList(cache, edges);

    const created: ChatSessionMetaFragment = {
      __typename: 'ChatSession',
      id: 'c',
      title: 'C',
      createdAt: '2024-01-03T00:00:00.000Z',
      updatedAt: '2024-01-04T00:00:00.000Z',
    };

    writeSessionMeta(cache, created);
    modifySessionMeta(cache, created);

    const result = cache.readQuery({
      query: ChatSessionListWithCursorDocument,
      variables: { first: 50 },
    });

    const cursor = Buffer.from(`${created.updatedAt}|${created.id}`, 'utf8').toString('base64');

    expect(result?.chatSessionList.edges[0]?.node.id).toBe('c');
    expect(result?.chatSessionList.edges[0]?.cursor).toBe(cursor);
    expect(result?.chatSessionList.edges[1]?.node.id).toBe('a');
  });
});
