'use client';

import { useRef, useEffect, useActionState } from 'react';
import type { ChatEdge, ChatNode } from '@/features/chat/chat.types';
import { useChatState, useChatActions } from '@/features/chat/chat.store';
import { usePathname, useRouter } from 'next/navigation';
import { useApolloClient } from '@apollo/client/react';

import { ChatSessionMetaFragment, ChatSessionMetaFragmentDoc } from '@/gql/graphql';
import {
  modifySessionMeta,
  openSessionEvents,
  writeSessionMeta,
} from '@/features/chat/chat.session.util';
import { openChatStream } from '@/features/chat/chat.stream.util';
import { useChatUI } from '@/providers/ChatProvider';
import { enqueueAction } from '@/actions/chat/enqueue.action';

type SubmitState = {
  error: string | null;
  jobId?: string;
};
const initialSubmitState: SubmitState = { error: null };

/**
 * Custom React hook managing a chat session stream.
 *
 * Handles optimistic UI updates by immediately adding the user's message,
 * then submits it via a React 19 action to the backend API.
 * It opens a server-sent events (SSE) stream to receive incremental assistant responses.
 * Supports session creation and updates, syncing session metadata in Apollo cache.
 * Integrates with React 19's action model for async state management and abort control.
 *
 * @param sessionId - Current chat session ID or null for new sessions
 * @returns state and actions related to chat messages, loading, errors, and submission
 */
export function useChatSessionStream(sessionId: string | null) {
  const router = useRouter();
  const pathname = usePathname();
  const { messages, loading, error } = useChatState();
  const {
    add,
    reset,
    setRag,
    getRag,
    updateStream,
    updateSources,
    updateRagSearch,
    updateToolCalls,
    markStreamDone,
  } =
    useChatActions();
  const hasMeta = useRef(false);
  const { adoptNewSession } = useChatUI();
  const client = useApolloClient();
  const hasAdoptedSession = useRef(false);

  const ctrl = useRef<AbortController | null>(null);

  /**
   * React 19 action state managing the submit lifecycle.
   *
   * Performs optimistic update by adding the user message immediately.
   * Sends the message to the backend, handling new session creation if needed.
   * Opens SSE streams for assistant responses and session event updates.
   * Supports aborting previous requests to prevent race conditions.
   */
  const [actionState, runSubmit] = useActionState<SubmitState, FormData>(
    async (prev, formData) => {
      const raw = formData.get('text') ?? formData.get('message');
      const text = typeof raw === 'string' ? raw : '';
      if (!text.trim()) return prev;

      const thisSessionId = sessionId ?? null;
      if (thisSessionId === null) {
        hasAdoptedSession.current = false;
      }
      const thisMode = getRag(thisSessionId);
      const userNode: ChatNode = { role: 'user', content: text };
      const userMsg: ChatEdge = { cursor: null, node: userNode };

      // Optimistic UI update: add user's message immediately
      add(userMsg);

      ctrl.current?.abort();
      ctrl.current = new AbortController();

      const jobId = crypto.randomUUID();

      // Add empty assistant message to stream updates into
      const assistantMsg: ChatEdge = {
        node: { role: 'assistant', content: '', jobId, streamDone: false },
      };
      add(assistantMsg);

      try {
        const enqueueResult = await enqueueAction({
          sessionId: thisSessionId,
          jobId: jobId,
          message: text,
          mode: thisMode ? 'rag' : 'gen',
        });

        if (!enqueueResult.success) {
          const errorNode: ChatNode = { role: 'system', content: `SSE open failed` };
          const errorMsg: ChatEdge = { cursor: null, node: errorNode };
          add(errorMsg);

          return { error: 'SSE open failed', jobId };
        }

        const { sessionId: createdId } = enqueueResult.data;

        if (thisSessionId) {
          const now = new Date().toISOString();
          const cacheId = client.cache.identify({ __typename: 'ChatSession', id: thisSessionId });
          const existing = cacheId
            ? client.readFragment<ChatSessionMetaFragment>({
                id: cacheId,
                fragment: ChatSessionMetaFragmentDoc,
              })
            : null;
          const next: ChatSessionMetaFragment = {
            __typename: 'ChatSession',
            id: thisSessionId,
            title: existing?.title ?? null,
            createdAt: existing?.createdAt ?? now,
            updatedAt: now,
          };
          writeSessionMeta(client.cache, next);
          modifySessionMeta(client.cache, next);
        }

        if (thisSessionId === null && createdId !== null) {
          hasAdoptedSession.current = true;
          adoptNewSession(createdId);
          const target = `/chat/${encodeURIComponent(createdId)}`;
          if (pathname !== target) {
            router.replace(target, { scroll: false });
          }
        }

        // Handle session creation and updates via SSE events
        if (thisSessionId === null) {
          openSessionEvents(jobId, {
            onCreated: s => {
              writeSessionMeta(client.cache, s);
              modifySessionMeta(client.cache, s);
              if (!hasAdoptedSession.current) {
                adoptNewSession(s.id);
              }
              setRag(s.id, thisMode);
            },
            onUpdated: s => {
              if (!s.id) return;
              const cacheId = client.cache.identify({ __typename: 'ChatSession', id: s.id });
              const existing = client.readFragment<ChatSessionMetaFragment>({
                id: cacheId,
                fragment: ChatSessionMetaFragmentDoc,
              });

              const next: ChatSessionMetaFragment = {
                __typename: 'ChatSession',
                id: s.id,
                title: s.title ?? existing?.title ?? null,
                createdAt: existing?.createdAt ?? new Date().toISOString(),
                updatedAt: s.updatedAt ?? existing?.updatedAt ?? new Date().toISOString(),
              };

              if (
                existing &&
                (existing.title ?? null) === (next.title ?? null) &&
                (existing.updatedAt ?? null) === (next.updatedAt ?? null)
              ) {
                return;
              }

              writeSessionMeta(client.cache, next);
            },
            onError: e => console.error('sessionEvents error', e),
          });
        }

        // Open SSE stream for assistant's incremental response
        openChatStream(jobId, {
          onText: chunk => updateStream(chunk, jobId),
          onSources: sources => updateSources(sources, jobId),
          onRagSearch: (meta, payload) => updateRagSearch(jobId, meta, payload),
          onToolCall: (meta, payload) => updateToolCalls(jobId, meta, payload),
          onDone: () => {
            hasMeta.current = false;
            markStreamDone(jobId);
          },
          onError: e => {
            markStreamDone(jobId);
            console.error('chatStream error', e);
          },
        });

        return { error: null, jobId };
      } catch (e) {
        const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : 'unknown error';
        const errorNode: ChatNode = { role: 'system', content: `❗ ${String(msg)}` };
        add({ cursor: null, node: errorNode });
        return { error: String(msg), jobId };
      }
    },
    initialSubmitState,
  );

  return {
    messages,
    loading,
    error: actionState.error ?? error,
    submitAction: runSubmit,
    add,
    reset,
    actionState,
  };
}
