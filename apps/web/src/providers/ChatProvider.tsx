'use client';

import {
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
  createContext,
  useContext,
  useCallback,
} from 'react';
import { chatSessionsStore } from '@/features/chat/chat.sessions.store';
import { useShallow } from 'zustand/react/shallow';
import { useParams } from 'next/navigation';
import { useChatActions } from '@/features/chat/chat.store';

type ChatUIValue = {
  busy: boolean;
  setBusy: (v: boolean) => void;
  awaitingFirstToken: boolean;
  setAwaitingFirstToken: (v: boolean) => void;
  adoptNewSession: (sid: string) => void;
  ensureLoaded: (
    sid: string,
    f: (sid: string, signal?: AbortSignal) => Promise<void>,
  ) => Promise<void> | void;
};

const ChatUIContext = createContext<ChatUIValue | undefined>(undefined);

export const useChatUI = (): ChatUIValue => {
  const ctx = useContext(ChatUIContext);
  if (!ctx) {
    throw new Error('useChatUI must be used within <ChatProvider>');
  }
  return ctx;
};

/**
 * ChatProvider: Maintains a persistent context across page transitions (router.replace),
 * including:
 * - A guard to load each session only once (loadedSet)
 * - Immediate activation and cache marking upon new session creation
 */
export default function ChatProvider({ children }: { children: ReactNode }) {
  const [busy, setBusy] = useState(false);
  const [awaitingFirstToken, setAwaitingFirstToken] = useState(false);

  // Subscribe only to required actions/state from the global store
  const { setActiveSessionId, setSelectedSessionId } = chatSessionsStore(
    useShallow(s => ({
      setActiveSessionId: s.setActiveSessionId, // Actual stream target
      setSelectedSessionId: s.setSelectedSessionId, // Sync if needed
    })),
  );

  // Guard to track first fetch per session
  const loadedSet = useRef<Set<string>>(new Set());
  // (Optional) Prevent concurrent requests per session
  const inflight = useRef<Map<string, Promise<void>>>(new Map());
  // AbortController to manage the current active session fetch
  const currentFetchAC = useRef<AbortController | null>(null);

  // Track previous route's sessionId to detect first entry from "/chat" (empty) to "/chat/:id"
  const prevRouteSid = useRef<string | null>(null);
  const createdSidRef = useRef<string | null>(null);

  // Guaranteed loader injected externally (fetcher)
  const ensureLoaded = useMemo(() => {
    return async (
      sid: string,
      fetchBySession: (sid: string, signal?: AbortSignal) => Promise<void>,
    ) => {
      if (!sid) return;
      if (loadedSet.current.has(sid)) return;
      if (inflight.current.has(sid)) return inflight.current.get(sid);

      const ac = new AbortController();
      const p = fetchBySession(sid, ac.signal)
        .then(() => {
          loadedSet.current.add(sid);
        })
        .finally(() => inflight.current.delete(sid));

      inflight.current.set(sid, p);
      return p;
    };
  }, []);

  const { fetchBySession, reset: resetChat } = useChatActions();
  const { sessionId: routeSessionIdRaw } = useParams<{ sessionId?: string }>();
  const routeSessionId = typeof routeSessionIdRaw === 'string' ? routeSessionIdRaw : null;

  /**
   * Called immediately after a new session is created (when createdSid is received from POST response):
   * - Fix activeSessionId immediately (stream/append target)
   * - Add createdSid to loadedSet to prevent refetching after replace
   * - Sync selected session if necessary
   */
  const adoptNewSession = useCallback(
    (createdSid: string) => {
      setActiveSessionId(createdSid);
      loadedSet.current.add(createdSid);
      setSelectedSessionId(createdSid);
      createdSidRef.current = createdSid;
    },
    [setActiveSessionId, setSelectedSessionId],
  );

  useEffect(() => {
    // Entering /chat (empty session): abort previous requests, reset message store, and clear stream target
    if (!routeSessionId) {
      currentFetchAC.current?.abort();
      currentFetchAC.current = null;
      resetChat();
      setActiveSessionId(null);
      prevRouteSid.current = null;
      createdSidRef.current = null;
      return;
    }

    // If previous route was empty session (null):
    // - Skip first fetch only if it's an automatic replace with the newly created session (createdSidRef)
    // - Otherwise, proceed with fetch (e.g., user clicked sidebar)
    if (prevRouteSid.current === null) {
      prevRouteSid.current = routeSessionId;
      if (createdSidRef.current === routeSessionId) {
        // Auto-routing (newly created) case → skip fetch
        return;
      }
      // Manual click case → proceed to fetch below
    }

    // On entering/changing session page, force fetch
    // Abort previous session fetch if ongoing
    if (createdSidRef.current === routeSessionId) {
      setActiveSessionId(routeSessionId);
      prevRouteSid.current = routeSessionId;
      createdSidRef.current = null;
      return;
    } else {
      resetChat();
      currentFetchAC.current?.abort();
      const ac = new AbortController();
      currentFetchAC.current = ac;
      prevRouteSid.current = routeSessionId;

      void fetchBySession(routeSessionId, ac.signal)
        .catch((err: Error) => {
          // Ignore AbortError, log others
          if (err?.name !== 'AbortError')
            console.warn('[ChatProvider] fetchBySession failed:', err);
        })
        .finally(() => {
          // Clear controller only if it's the current one
          if (currentFetchAC.current === ac) {
            currentFetchAC.current = null;
          }
        });
    }
  }, [routeSessionId, fetchBySession, resetChat, setActiveSessionId]);

  useEffect(() => {
    return () => {
      currentFetchAC.current?.abort();
      currentFetchAC.current = null;
    };
  }, []);

  // Could be provided via Context or global singleton.
  // Here, just wrap children.
  return (
    <ChatUIContext.Provider
      value={{
        busy,
        setBusy,
        awaitingFirstToken,
        setAwaitingFirstToken,
        adoptNewSession,
        ensureLoaded,
      }}
    >
      {children}
    </ChatUIContext.Provider>
  );
}
