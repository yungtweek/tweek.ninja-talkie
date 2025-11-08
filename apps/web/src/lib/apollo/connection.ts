import type { ApolloCache, DocumentNode, Reference } from '@apollo/client';
import type { TypedDocumentNode } from '@graphql-typed-document-node/core';
import type { StoreObject } from '@apollo/client/utilities';

type EdgeRef = { __ref: string };
type EdgeNode = { __typename?: string; node?: Reference };
type AnyEdge = EdgeRef | EdgeNode;

const isRef = (v: unknown): v is Reference =>
  typeof v === 'object' && v !== null && '__ref' in (v as any);

/** 커넥션에서 특정 id의 노드를 제거 */
export function removeFromConnection(
  cache: ApolloCache,
  opts: {
    fieldName: string;
    id: string;
  },
) {
  cache.modify({
    fields: {
      [opts.fieldName](existing: StoreObject | Reference | undefined, { readField }) {
        if (!existing || isRef(existing)) return existing;

        const store = existing as StoreObject & { edges?: AnyEdge[] };
        const edges = store.edges ?? [];
        if (!Array.isArray(edges) || edges.length === 0) return existing;

        const nextEdges = edges.filter(edge => {
          let ref: Reference | undefined;
          if ('node' in edge && edge.node) ref = edge.node;
          else if ('__ref' in edge) ref = { __ref: edge.__ref } as Reference;
          if (!ref) return true;
          return readField('id', ref) !== opts.id;
        });

        return { ...store, edges: nextEdges } as StoreObject;
      },
    },
  });
}

export function upsertIntoConnection<
  TData extends { __typename: string; id: string },
  TFragment = TData,
>(
  cache: ApolloCache,
  opts: {
    fieldName: string;
    fragment: TypedDocumentNode<TFragment, any> | DocumentNode;
    data: TData;
    position?: 'prepend' | 'append';
  },
): boolean {
  const newRef = cache.writeFragment<TData>({
    fragment: opts.fragment as unknown as DocumentNode,
    data: opts.data,
  });

  let added = false;

  cache.modify({
    fields: {
      [opts.fieldName](existing: StoreObject | Reference | undefined, { readField }) {
        if (!existing || isRef(existing)) return existing;

        const store = existing as StoreObject & { edges?: AnyEdge[] };
        const edges = store.edges ?? [];

        const alreadyThere = edges.some(edge => {
          const ref =
            'node' in edge && edge.node
              ? edge.node
              : '__ref' in edge
                ? ({ __ref: edge.__ref } as Reference)
                : undefined;
          return ref ? readField('id', ref) === opts.data.id : false;
        });
        if (alreadyThere) return existing;

        const edge: AnyEdge = { __typename: 'FileEdge', node: newRef as Reference };
        const nextEdges: AnyEdge[] =
          opts.position === 'append' ? [...edges, edge] : [edge, ...edges];
        added = true;
        return { ...store, edges: nextEdges } as StoreObject;
      },
    },
  });
  return added;
}
