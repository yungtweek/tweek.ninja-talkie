// apps/web/src/lib/apollo.client.ts
import { ApolloClient, InMemoryCache, ApolloLink } from '@apollo/client';
import { GraphQLWsLink } from '@apollo/client/link/subscriptions';
import { createClient } from 'graphql-ws';
import { getMainDefinition } from '@apollo/client/utilities';
import { getCookie } from 'cookies-next';

import { link } from './apollo.links';
import { Kind, OperationTypeNode } from 'graphql/language';

const wsLink =
  typeof window !== 'undefined'
    ? new GraphQLWsLink(
        createClient({
          url: process.env.NEXT_PUBLIC_GQL_WS_URL!,
          connectionParams: () => {
            const token = getCookie('access_token');
            if (typeof token === 'string' && token.trim() !== '') {
              return { Authorization: `Bearer ${token}` };
            }
            return {};
          },
        }),
      )
    : null;

const splitLink =
  typeof window !== 'undefined' && wsLink
    ? ApolloLink.split(
        ({ query }) => {
          const def = getMainDefinition(query);
          return (
            def.kind === Kind.OPERATION_DEFINITION &&
            def.operation === OperationTypeNode.SUBSCRIPTION
          );
        },
        wsLink,
        link,
      )
    : link;

export const apolloClient = new ApolloClient({
  link: splitLink,
  cache: new InMemoryCache(),
});
