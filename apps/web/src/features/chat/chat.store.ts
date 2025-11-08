import { create } from 'zustand';
import { ChatEdge } from '@/features/chat/chat.types';
import { useShallow } from 'zustand/react/shallow';
import { apolloClient } from '@/lib/apollo/apollo.client';
import { ChatSessionDocument } from '@/gql/graphql';
import type { ChatSessionQuery, ChatSessionQueryVariables } from '@/gql/graphql';
import { z } from 'zod';

interface ChatState {
  edges: ChatEdge[];
  loading: boolean;
  error: string | null;

  fetchBySession: (sessionId: string | null, signal?: AbortSignal) => Promise<void>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  add: (m: ChatEdge) => void;
  appendLive: (token: string, jobId: string) => void;
  reset: () => void;

  ragBySession: Record<string, boolean>;
  pendingRag: boolean; // ✅ Temporary RAG before session creation
  getRag: (sessionId: string | null) => boolean;
  setRag: (sessionId: string | null, value: boolean) => void;
  toggleRag: (sessionId: string | null) => void;
  adoptPendingRag: (sessionId: string) => void; // ✅ Assign temporary value to new session
}

export const chatStore = create<ChatState>((set, get) => ({
  edges: [],
  loading: false,
  busy: false,
  setBusy: (value: boolean) => set({ busy: value }),
  error: null,

  ragBySession: {},
  pendingRag: false,

  getRag: (sessionId: string | null) => {
    if (!sessionId) return get().pendingRag; // ✅ Temporary value for new chat in UI
    return get().ragBySession[sessionId] ?? false;
  },
  setRag: (sessionId: string | null, value: boolean) => {
    if (!sessionId) {
      // ✅ Update only temporary value
      set({ pendingRag: value });
      return;
    }
    set(state => ({
      ragBySession: {
        ...state.ragBySession,
        [sessionId]: value,
      },
    }));
  },
  toggleRag: (sessionId: string | null) => {
    if (!sessionId) {
      // ✅ Toggle temporary value
      set(s => ({ pendingRag: !s.pendingRag }));
      return;
    }
    set(state => ({
      ragBySession: {
        ...state.ragBySession,
        [sessionId]: !(state.ragBySession[sessionId] ?? false),
      },
    }));
  },

  adoptPendingRag: (sessionId: string) => {
    const { pendingRag } = get();
    set(s => ({
      ragBySession: { ...s.ragBySession, [sessionId]: pendingRag },
      // You can choose to keep or reset pendingRag. Usually keeping it is convenient.
      // pendingRag: false,
    }));
  },

  fetchBySession: async (sessionId, signal) => {
    set({ loading: true, error: null });
    if (sessionId === null) {
      set({ edges: [], loading: false });
      return;
    }
    try {
      const valid = z.uuid().safeParse(sessionId).success;

      if (!valid) {
        console.error('Invalid session ID:', sessionId);
        set({ loading: false, error: 'Invalid session ID' });
        return;
      }
      const { data } = await apolloClient.query<ChatSessionQuery, ChatSessionQueryVariables>({
        query: ChatSessionDocument,
        variables: { id: sessionId },
        fetchPolicy: 'no-cache',
        context: { fetchOptions: { signal } },
      });
      console.log('fetchBySession', sessionId);
      const edges = (data?.chatSession?.messages?.edges ?? []) as ChatEdge[];
      set({ edges, loading: false });
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') return;
      set({ loading: false, error: e instanceof Error ? e.message : String(e) });
    }
  },

  add: m =>
    set(st => ({
      edges: [...st.edges, m],
    })),

  appendLive: (token, jobId) =>
    set(st => {
      // Input validation: ignore empty chunks
      if (!token || token.length === 0) return { edges: st.edges };
      // Find target message: identify only by jobId
      const idx = st.edges.findIndex(m => m?.node.jobId === jobId);
      if (idx < 0) return { edges: st.edges };

      const target = st.edges[idx];
      // Reflect stream only for assistant messages
      if (!target || target.node?.role !== 'assistant') {
        return { edges: st.edges };
      }

      // Nested immutable update
      const updated: ChatEdge = {
        ...target,
        node: {
          ...target.node,
          content: (target.node.content ?? '') + String(token),
        },
      };

      const next = st.edges.slice();
      next[idx] = updated;
      return { edges: next };
    }),

  reset: () => set({ edges: [], loading: false, error: null }),
}));

// Selector hook (to minimize re-renders)
export function useChatState() {
  return chatStore(
    useShallow(s => ({
      messages: s.edges,
      loading: s.loading,
      busy: s.busy,
      setBusy: s.setBusy,
      error: s.error,
      pendingRag: s.pendingRag,
      ragBySession: s.ragBySession,
    })),
  );
}

export function useChatActions() {
  return chatStore(
    useShallow(s => ({
      fetchBySession: s.fetchBySession,
      setRag: s.setRag,
      getRag: s.getRag,
      toggleRag: s.toggleRag,
      adoptPendingRag: s.adoptPendingRag,
      add: s.add,
      updateStream: s.appendLive,
      // updateCitations: s.updateCitations,
      reset: s.reset,
    })),
  );
}
