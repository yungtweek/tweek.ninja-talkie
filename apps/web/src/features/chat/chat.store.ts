import { create } from 'zustand';
import {
  ChatEdge,
  ChatNode,
  RagEventMeta,
  RagEventPayload,
  RagSearchSnapshot,
  RagStageSnapshot,
  RagWrapperSnapshot,
  ToolCallSnapshot,
  ToolCallPayload,
  ToolCallsSnapshot,
  ToolEventMeta,
} from '@/features/chat/chat.types';
import { useShallow } from 'zustand/react/shallow';
import { apolloClient } from '@/lib/apollo/apollo.client';
import { ChatSessionDocument } from '@/gql/graphql';
import type { ChatSessionQuery, ChatSessionQueryVariables } from '@/gql/graphql';
import { z } from 'zod';
import { safeJsonParse } from '@/lib/utils';

export const selectIsStreaming = (edges: ChatEdge[]) =>
  edges.some(m => m?.node?.role === 'assistant' && m?.node?.streamDone === false);

interface ChatState {
  edges: ChatEdge[];
  loading: boolean;
  error: string | null;

  fetchBySession: (sessionId: string | null, signal?: AbortSignal) => Promise<void>;
  add: (m: ChatEdge) => void;
  appendLive: (token: string, jobId: string) => void;
  updateSources: (sources: unknown, jobId: string) => void;
  updateRagSearch: (
    jobId: string,
    meta: RagEventMeta,
    payload?: RagEventPayload,
  ) => void;
  updateToolCalls: (
    jobId: string,
    meta: ToolEventMeta,
    payload?: ToolCallPayload,
  ) => void;
  markStreamDone: (jobId: string) => void;
  reset: () => void;

  ragBySession: Record<string, boolean>;
  pendingRag: boolean; // ✅ Temporary RAG before session creation
  getRag: (sessionId: string | null) => boolean;
  setRag: (sessionId: string | null, value: boolean) => void;
  toggleRag: (sessionId: string | null) => void;
  adoptPendingRag: (sessionId: string) => void; // ✅ Assign temporary value to new session
}

const updateEdgeByJobId = (
  edges: ChatEdge[],
  jobId: string,
  updateNode: (node: ChatNode) => ChatNode,
): ChatEdge[] => {
  if (!jobId) return edges;
  const idx = edges.findIndex(m => m?.node.jobId === jobId);
  if (idx < 0) return edges;

  const target = edges[idx];
  if (!target || target.node?.role !== 'assistant') {
    return edges;
  }

  const updated: ChatEdge = {
    ...target,
    node: updateNode(target.node),
  };

  const next = edges.slice();
  next[idx] = updated;
  return next;
};

export const chatStore = create<ChatState>((set, get) => ({
  edges: [],
  loading: false,
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
      const next = updateEdgeByJobId(st.edges, jobId, node => ({
        ...node,
        content: (node.content ?? '') + String(token),
      }));
      return { edges: next };
    }),

  updateSources: (sources, jobId) =>
    set(st => {
      if (sources == null) return { edges: st.edges };
      const payload = typeof sources === 'string' ? sources : JSON.stringify(sources);
      const next = updateEdgeByJobId(st.edges, jobId, node => ({
        ...node,
        sourcesJson: payload,
      }));
      return { edges: next };
    }),

  updateRagSearch: (jobId, meta, payload) =>
    set(st => {
      const next = updateEdgeByJobId(st.edges, jobId, node => ({
        ...node,
        ragSearchJson: (() => {
          const parsed = safeJsonParse<RagSearchSnapshot | Record<string, unknown>>(
            node.ragSearchJson,
            {},
          );
          const normalized: RagSearchSnapshot = {
            wrapper: {},
            stages: {},
          };
          if (parsed && ('wrapper' in parsed || 'stages' in parsed)) {
            if (parsed.wrapper) {
              normalized.wrapper = { ...parsed.wrapper };
            }
            if (parsed.stages) {
              normalized.stages = { ...parsed.stages };
            }
          }

          if (!node.ragSearchJson && node.ragSearch) {
            const { meta: priorMeta, payload: priorPayload } = node.ragSearch;
            const target =
              priorMeta.scope === 'wrapper'
                ? normalized.wrapper?.searchCall ?? { inProgress: null, completed: null }
                : (normalized.stages?.[priorMeta.key] ?? {
                    inProgress: null,
                    completed: null,
                  });
            if (priorMeta.status === 'in_progress' && !target.inProgress) {
              target.inProgress = priorPayload ?? null;
            }
            if (priorMeta.status === 'completed' && !target.completed) {
              target.completed = priorPayload ?? null;
            }
            if (priorMeta.scope === 'wrapper') {
              normalized.wrapper = { ...(normalized.wrapper ?? {}), searchCall: target };
            } else {
              normalized.stages = { ...(normalized.stages ?? {}), [priorMeta.key]: target };
            }
          }

          const stageSnapshot: RagStageSnapshot | RagWrapperSnapshot =
            meta.scope === 'wrapper'
              ? normalized.wrapper?.searchCall ?? { inProgress: null, completed: null }
              : (normalized.stages?.[meta.key] ?? {
                  inProgress: null,
                  completed: null,
                });

          if (meta.status === 'in_progress') {
            stageSnapshot.inProgress = {
              ...(stageSnapshot.inProgress ?? {}),
              ...(payload ?? {}),
            };
          } else {
            stageSnapshot.completed = {
              ...(stageSnapshot.completed ?? {}),
              ...(payload ?? {}),
            };
          }
          if (meta.scope === 'wrapper') {
            normalized.wrapper = { ...(normalized.wrapper ?? {}), searchCall: stageSnapshot };
          } else {
            normalized.stages = {
              ...(normalized.stages ?? {}),
              [meta.key]: stageSnapshot,
            };
          }

          return JSON.stringify(normalized);
        })(),
        ragSearch: undefined,
      }));
      return { edges: next };
    }),

  updateToolCalls: (jobId, meta, payload) =>
    set(st => {
      if (!payload) return { edges: st.edges };
      const next = updateEdgeByJobId(st.edges, jobId, node => {
        const parsed = safeJsonParse<ToolCallsSnapshot | Record<string, unknown>>(
          node.toolCallsJson,
          {},
        );
        const normalized: ToolCallsSnapshot = {
          order: [],
          calls: {},
        };
        if (parsed && typeof parsed === 'object') {
          const order = (parsed as ToolCallsSnapshot).order;
          if (Array.isArray(order)) {
            normalized.order = [...order];
          }
          const calls = (parsed as ToolCallsSnapshot).calls;
          if (calls && typeof calls === 'object') {
            normalized.calls = { ...(calls as Record<string, ToolCallSnapshot>) };
          }
        }

        const callId = payload.callId ?? payload.tool ?? '';
        if (!callId) {
          return node;
        }

        const existing = normalized.calls?.[callId];
        const entry: ToolCallSnapshot = existing ? { ...existing } : {};
        const nextEntry: ToolCallSnapshot = {
          ...entry,
          tool: payload.tool ?? entry.tool,
          attempt: payload.attempt ?? entry.attempt,
        };

        if (meta.status === 'in_progress') {
          nextEntry.inProgress = {
            ...(entry.inProgress ?? {}),
            ...payload,
          };
        } else {
          nextEntry.completed = {
            ...(entry.completed ?? {}),
            ...payload,
          };
        }

        normalized.calls = { ...(normalized.calls ?? {}), [callId]: nextEntry };
        if (!normalized.order?.includes(callId)) {
          normalized.order = [...(normalized.order ?? []), callId];
        }

        return {
          ...node,
          toolCallsJson: JSON.stringify(normalized),
        };
      });
      return { edges: next };
    }),

  markStreamDone: jobId =>
    set(st => {
      const next = updateEdgeByJobId(st.edges, jobId, node => ({
        ...node,
        streamDone: true,
      }));
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
      error: s.error,
      pendingRag: s.pendingRag,
      ragBySession: s.ragBySession,
    })),
  );
}

export function useChatStreaming() {
  return chatStore(s => selectIsStreaming(s.edges));
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
      updateSources: s.updateSources,
      updateRagSearch: s.updateRagSearch,
      updateToolCalls: s.updateToolCalls,
      markStreamDone: s.markStreamDone,
      reset: s.reset,
    })),
  );
}
