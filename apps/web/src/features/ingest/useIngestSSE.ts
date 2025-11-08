// useIngestSSE.ts
'use client';
import { useCallback, useEffect, useMemo } from 'react';
import { useApolloClient } from '@apollo/client/react';
import { createDedupe } from '@/lib/events/dedupe';
import { FileListType, FileMetaFragmentDoc } from '@/gql/graphql';
import { removeFromConnection, upsertIntoConnection } from '@/lib/apollo/connection';
import { useEventSource } from '@/features/ingest/useEventSource';
import { IngestEvent, IngestEventType } from '@talkie/events-contracts';

import {
  toGqlStatus,
  toGqlVisibility,
  writeFileStatus,
  writeFileVisibility,
} from '@/features/ingest/ingest.utils';
import { SSEErrorMeta } from '@/app/api/ingest/events/route';

export function useIngestSSE() {
  const client = useApolloClient();
  const dedupe = useMemo(() => createDedupe({ ttlMs: 1500, maxKeys: 500 }), []);

  // TODO
  const handleUnauthorized = useCallback((meta?: SSEErrorMeta) => {
    if (!meta) return;
    const refreshed = meta.refreshed === '1' || meta.refreshed?.toLowerCase?.() === 'true';
    console.log('refreshed', refreshed);
  }, []);

  const es = useEventSource({
    url: '/api/ingest/events',
    withCredentials: true,
    heartbeatEvent: 'ping',
    onUnauthorizedAction: handleUnauthorized,
  });

  useEffect(() => {
    const off1 = es.addEventListener(IngestEventType.REGISTERED, e => {
      const { payload } = JSON.parse(e.data) as {
        payload: FileListType;
      };
      if (dedupe([payload.id, payload.status])) return;
      upsertIntoConnection(client.cache, {
        fieldName: 'files',
        fragment: FileMetaFragmentDoc,
        data: { __typename: 'FileListType', ...payload },
      });
    });

    const off2 = es.addEventListener(IngestEventType.STATUS_CHANGED, e => {
      const evt = JSON.parse(e.data) as IngestEvent;
      if (evt.type !== IngestEventType.STATUS_CHANGED) return;
      const { payload } = evt;
      if (dedupe([payload.id, payload.next])) return;
      writeFileStatus(client.cache, payload.id, toGqlStatus(payload.next));
    });

    const off3 = es.addEventListener(IngestEventType.VISIBILITY_CHANGED, e => {
      const evt = JSON.parse(e.data) as IngestEvent;
      if (evt.type !== IngestEventType.VISIBILITY_CHANGED) return;
      const { payload } = evt;
      if (dedupe([payload.id, payload.next])) return;
      writeFileVisibility(client.cache, payload.id, toGqlVisibility(payload.next));
    });

    const off4 = es.addEventListener(IngestEventType.DELETED, e => {
      const evt = JSON.parse(e.data) as IngestEvent;
      if (evt.type !== IngestEventType.DELETED) return;
      const { payload } = evt;
      if (dedupe([payload.id, 'deleted'])) return;
      const cacheId = client.cache.identify({ __typename: 'FileListType', id: payload.id });
      if (cacheId) {
        client.cache.evict({ id: cacheId });
        removeFromConnection(client.cache, { fieldName: 'files', id: payload.id });
        client.cache.gc();
      }
    });

    return () => {
      off1?.();
      off2?.();
      off3?.();
      off4?.();
    };
  }, [client, es, dedupe]);

  return { state: es.state, isConnected: es.isConnected, lastBeatAt: es.lastBeatAt };
}
