// useEventSource.ts
/**
 * React hook for managing an EventSource connection with built-in reconnection,
 * heartbeat detection, and unauthorized event handling.
 *
 * Use this hook when you need a resilient SSE connection that handles stale
 * connections, retries with backoff, and custom unauthorized events.
 *
 * Example:
 * const { state, isConnected, start, stop } = useEventSource({ url: '/api/events' });
 */

'use client';
import { useEffect, useRef, useCallback, useReducer } from 'react';
import { SSEErrorMeta } from '@/app/api/ingest/events/route';

// Prevent stale closures by using a ref wrapper for event callbacks.
// We don't use useEffectEvent directly for compatibility with React 18/19.
function useEventCallback<T extends (...args: any[]) => any>(fn: T): T {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  }, [fn]);
  // eslint-disable-next-line @typescript-eslint/no-unsafe-return,@typescript-eslint/no-unsafe-argument
  return useCallback(((...args: any[]) => ref.current(...args)) as T, []);
}

// Finite state machine statuses for EventSource connection lifecycle.
type ESStatus = 'connecting' | 'open' | 'reconnecting' | 'stale' | 'closed';

// State shape to track connection status, last heartbeat, and retry attempts.
type State = {
  status: ESStatus;
  lastBeat: number;
  attempt: number;
};

// Events driving the FSM transitions for connection management.
type Event =
  | { type: 'START' } // initiate connection attempt
  | { type: 'OPEN' } // connection established
  | { type: 'HEARTBEAT'; at: number } // heartbeat received, update lastBeat
  | { type: 'ERROR' } // unrecoverable error, close connection
  | { type: 'UNAUTHORIZED' } // custom unauthorized event received
  | { type: 'RECONNECTING' } // retrying connection after delay
  | { type: 'CLOSED' } // connection closed explicitly
  | { type: 'STALE' }; // connection considered stale (no heartbeat)

type UseEventSourceOpts = {
  url: string; // SSE endpoint URL
  withCredentials?: boolean; // include credentials in request
  heartbeatEvent?: string; // event name to treat as heartbeat (default 'ping')
  staleAfterMs?: number; // ms without heartbeat before marking stale
  retryDelayMs?: number | ((attempt: number) => number); // backoff delay for reconnects
  onUnauthorizedAction?: (meta?: SSEErrorMeta) => boolean | void | Promise<boolean | void>; // handler for unauthorized event
};

function esReducer(state: State, evt: Event): State {
  switch (evt.type) {
    case 'START':
      // Begin connecting
      return { ...state, status: 'connecting' };
    case 'OPEN':
      // Connection opened successfully, reset attempt counter
      return { status: 'open', lastBeat: Date.now(), attempt: 0 };
    case 'HEARTBEAT':
      // Update lastBeat timestamp; if stale, mark open again
      return {
        ...state,
        lastBeat: evt.at,
        status: state.status === 'stale' ? 'open' : state.status,
      };
    case 'ERROR':
      // Unrecoverable error: close connection
      return { ...state, status: 'closed' };
    case 'UNAUTHORIZED':
      // Unauthorized event: close and expect external reconnect policy
      return { ...state, status: 'closed' };
    case 'RECONNECTING':
      // Trigger reconnect attempt, increment attempt count
      return { ...state, status: 'reconnecting', attempt: state.attempt + 1 };
    case 'CLOSED':
      // Explicitly closed connection
      return { ...state, status: 'closed' };
    case 'STALE':
      // Mark connection stale only if currently open
      return state.status === 'open' ? { ...state, status: 'stale' } : state;
    default:
      return state;
  }
}

export function useEventSource(opts: UseEventSourceOpts) {
  const {
    url,
    withCredentials = true,
    heartbeatEvent = 'ping',
    staleAfterMs = 20_000,
    retryDelayMs = (n: number) => Math.min(1000 * 2 ** n, 10_000),
    onUnauthorizedAction,
  } = opts;

  const esRef = useRef<EventSource | null>(null);
  const mounted = useRef(true);
  const [state, dispatch] = useReducer(esReducer, {
    status: 'connecting',
    lastBeat: Date.now(),
    attempt: 0,
  });

  // Wrap unauthorized handler to avoid stale closure issues
  const handleUnauthorized = useEventCallback(async (meta?: SSEErrorMeta) => {
    await onUnauthorizedAction?.(meta);
  });

  // Wrap heartbeat handler similarly for stable callback reference
  const handleHeartbeat = useEventCallback(() => {
    dispatch({ type: 'HEARTBEAT', at: Date.now() });
  });

  // Attach stable listeners to EventSource; returns cleanup function.
  // onBeat wrapper needed to keep stable reference for add/removeEventListener.
  // onerror closes connection to prevent browser auto-retry loops.
  // unauthorized event closes connection and triggers external policy.
  const applyListeners = useCallback(
    (es: EventSource) => {
      es.onopen = () => {
        dispatch({ type: 'OPEN' });
      };
      es.onerror = () => {
        // Close on unhandleable error to stop browser auto-retry.
        es.close();
        dispatch({ type: 'ERROR' });
      };
      // heartbeat event listener
      const onBeat = () => {
        handleHeartbeat();
      };
      es.addEventListener(heartbeatEvent, onBeat as EventListener);

      // unauthorized custom event listener
      const onUnauthorizedEvt = (e: any) => {
        console.log(e);
        es.close();
        dispatch({ type: 'UNAUTHORIZED' });
        void handleUnauthorized();
        reconnect();
      };
      es.addEventListener('unauthorized', onUnauthorizedEvt as EventListener, { once: true });

      return () => {
        es.removeEventListener(heartbeatEvent, onBeat as EventListener);
        es.removeEventListener('unauthorized', onUnauthorizedEvt as EventListener);
      };
    },
    [heartbeatEvent, handleUnauthorized, handleHeartbeat],
  );

  // Start connection; dispatch START and apply listeners.
  // Returns a detach function to clean up listeners and close connection.
  const start = useCallback(() => {
    stop(); // ensure clean start
    dispatch({ type: 'START' });
    const es = new EventSource(url, { withCredentials });
    esRef.current = es;
    const detach = applyListeners(es);
    return () => {
      detach();
      es.close();
    };
  }, [url, withCredentials, applyListeners]);

  // Stop connection; idempotent close and clear ref.
  const stop = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    dispatch({ type: 'CLOSED' });
  }, []);

  // Reconnect with backoff delay based on attempt count.
  // Guard with mounted ref to avoid reconnecting after unmount.
  const reconnect = useCallback(() => {
    const delay = typeof retryDelayMs === 'function' ? retryDelayMs(state.attempt) : retryDelayMs;
    stop();
    dispatch({ type: 'RECONNECTING' }); // attempt incremented in reducer
    setTimeout(() => {
      if (mounted.current) start();
    }, delay);
  }, [retryDelayMs, start, stop, state.attempt]);

  // Periodic stale detection: marks stale instead of reconnecting immediately
  // to allow external handling or manual reconnection.
  useEffect(() => {
    const t = setInterval(() => {
      if (state.status === 'open' && Date.now() - state.lastBeat > staleAfterMs)
        dispatch({ type: 'STALE' });
    }, 5000);
    return () => clearInterval(t);
  }, [state.status, state.lastBeat, staleAfterMs]);

  // Lifecycle effect: mark mounted, start connection, and detach on unmount/deps change.
  useEffect(() => {
    mounted.current = true;
    const detach = start();
    return () => {
      mounted.current = false;
      detach?.();
    };
  }, [start]);

  // Convenience wrapper to add/remove external event listeners on the EventSource.
  // Provides symmetrical API to native addEventListener.
  const add = useCallback((type: string, handler: (e: MessageEvent<string>) => void) => {
    esRef.current?.addEventListener(type, handler as EventListener);
    return () => esRef.current?.removeEventListener(type, handler as EventListener);
  }, []);

  // Return state and controls for consumer to manage connection and listen to events.
  return {
    state,
    isConnected: state.status === 'open',
    lastBeatAt: new Date(state.lastBeat),
    start,
    stop,
    reconnect,
    addEventListener: add,
    get readyState() {
      return esRef.current?.readyState;
    },
  };
}
