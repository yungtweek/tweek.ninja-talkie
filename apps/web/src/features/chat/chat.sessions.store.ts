'use client';
import { create } from 'zustand';
import { ChatSessionZod } from '@talkie/types-zod';
import { useShallow } from 'zustand/react/shallow';

const _loadedSessions = new Set<string>();
const _inflightSessions = new Map<string, Promise<void>>();

type SessionsState = {
  sessionList: ChatSessionZod[];
  selectedSessionId: string | null;
  activeSessionId: string | null;
  reloadKey: number;

  setSessionList: (list: ChatSessionZod[]) => void;
  upsertSession: (s: ChatSessionZod) => void;
  removeById: (id: string) => void;
  setSelectedSessionId: (id: string | null) => void;
  setActiveSessionId: (id: string | null) => void;
  bumpReload: () => void;
  reset: () => void;

  hasLoaded: (id: string) => boolean;
  markLoaded: (id: string) => void;
  ensureLoaded: (
    id: string,
    fetcher: (sid: string, signal?: AbortSignal) => Promise<void>,
  ) => Promise<void | undefined>;
};

export const chatSessionsStore = create<SessionsState>(set => ({
  sessionList: [],
  selectedSessionId: null,
  activeSessionId: null,
  reloadKey: 0,
  setSessionList: list => set({ sessionList: list }),
  upsertSession: s =>
    set(st => {
      const idx = st.sessionList.findIndex(x => x.id === s.id);

      if (idx < 0) {
        return { sessionList: [s, ...st.sessionList] };
      }

      const old = st.sessionList[idx];
      if (
        old.title === s.title &&
        (old as any).last_message_at === (s as any).last_message_at &&
        (old as any).last_message_preview === (s as any).last_message_preview
      ) {
        return { sessionList: st.sessionList };
      }

      const next = st.sessionList.slice();
      next.splice(idx, 1);
      return { sessionList: [s, ...next] };
    }),
  removeById: id => set(st => ({ sessionList: st.sessionList.filter(s => s.id !== id) })),
  setSelectedSessionId: id => set({ selectedSessionId: id }),
  setActiveSessionId: id => set({ activeSessionId: id }),
  bumpReload: () => set(st => ({ reloadKey: st.reloadKey + 1 })),
  hasLoaded: id => _loadedSessions.has(id),
  markLoaded: id => {
    _loadedSessions.add(id);
    return undefined as unknown as void;
  },
  ensureLoaded: async (id, fetcher) => {
    if (!id) return;
    if (_loadedSessions.has(id)) return;
    const existing = _inflightSessions.get(id);
    if (existing) return existing;
    const ac = new AbortController();
    const p = fetcher(id, ac.signal)
      .then(() => {
        _loadedSessions.add(id);
      })
      .finally(() => {
        _inflightSessions.delete(id);
      });
    _inflightSessions.set(id, p);
    return p;
  },
  reset: () => {
    _loadedSessions.clear();
    _inflightSessions.clear();
    set({ sessionList: [], selectedSessionId: null, activeSessionId: null, reloadKey: 0 });
  },
}));

export function useSessionsState() {
  return chatSessionsStore(
    useShallow(s => ({
      sessionList: s.sessionList,
      selectedSessionId: s.selectedSessionId,
      reloadKey: s.reloadKey,
    })),
  );
}

export function useSessionsActions() {
  return chatSessionsStore(
    useShallow(s => ({
      selectedSessionId: s.selectedSessionId,
      setSessionList: s.setSessionList,
      removeById: s.removeById,
      upsertSession: s.upsertSession,
      setSelectedSessionId: s.setSelectedSessionId,
      setActiveSessionId: s.setActiveSessionId,
      bumpReload: s.bumpReload,
      reset: s.reset,
    })),
  );
}
