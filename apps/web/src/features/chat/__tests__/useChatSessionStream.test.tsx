/** @jest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';

jest.mock('react', () => {
  const actual = jest.requireActual('react');
  return {
    ...actual,
    useActionState: (action: (state: any, formData: FormData) => Promise<any>, initial: any) => {
      let state = initial;
      const dispatch = async (formData: FormData) => {
        state = await action(state, formData);
        return state;
      };
      return [state, dispatch];
    },
  };
});
import { useChatSessionStream } from '@/features/chat/useChatSessionStream';
import { enqueueAction } from '@/actions/chat/enqueue.action';
import { modifySessionMeta, writeSessionMeta } from '@/features/chat/chat.session.util';

let mockCache: {
  identify: jest.Mock;
  readFragment: jest.Mock;
};
const adoptNewSession = jest.fn();
const routerReplace = jest.fn();
let pathname = '/chat/session-1';

jest.mock('@apollo/client/react', () => ({
  useApolloClient: () => ({
    cache: mockCache,
    readFragment: (...args: any[]) => mockCache.readFragment(...args),
  }),
}));

const add = jest.fn();
const reset = jest.fn();
const setRag = jest.fn();
const getRag = jest.fn(() => false);
const updateStream = jest.fn();
const updateSources = jest.fn();
const updateRagSearch = jest.fn();
const updateToolCalls = jest.fn();
const markStreamDone = jest.fn();

jest.mock('@/features/chat/chat.store', () => ({
  useChatState: () => ({ messages: [], loading: false, error: null }),
  useChatActions: () => ({
    add,
    reset,
    setRag,
    getRag,
    updateStream,
    updateSources,
    updateRagSearch,
    updateToolCalls,
    markStreamDone,
  }),
}));

jest.mock('@/providers/ChatProvider', () => ({
  useChatUI: () => ({ adoptNewSession }),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace }),
  usePathname: () => pathname,
}));

jest.mock('@/actions/chat/enqueue.action', () => ({
  enqueueAction: jest.fn(),
}));

jest.mock('@/features/chat/chat.stream.util', () => ({
  openChatStream: jest.fn(),
}));

jest.mock('@/features/chat/chat.session.util', () => ({
  modifySessionMeta: jest.fn(),
  writeSessionMeta: jest.fn(),
  openSessionEvents: jest.fn(() => ({ close: jest.fn() })),
}));

describe('useChatSessionStream', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pathname = '/chat/session-1';
    mockCache = {
      identify: jest.fn().mockReturnValue('ChatSession:session-1'),
      readFragment: jest.fn().mockReturnValue({
        __typename: 'ChatSession',
        id: 'session-1',
        title: 'Title',
        createdAt: '2024-01-01T00:00:00.000Z',
        updatedAt: '2024-01-01T00:00:00.000Z',
      }),
    };
    (globalThis as { crypto?: { randomUUID: () => string } }).crypto = {
      randomUUID: () => 'job-1',
    };
  });

  it('moves the session after enqueue succeeds', async () => {
    (enqueueAction as jest.Mock).mockResolvedValueOnce({
      success: true,
      data: { sessionId: 'session-1' },
    });

    const { result } = renderHook(() => useChatSessionStream('session-1'));
    const fd = new FormData();
    fd.set('text', 'hello');

    await act(async () => {
      await result.current.submitAction(fd);
    });

    await waitFor(() => {
      expect(writeSessionMeta).toHaveBeenCalledTimes(1);
      expect(modifySessionMeta).toHaveBeenCalledTimes(1);
      expect(routerReplace).not.toHaveBeenCalled();
    });
  });

  it('does not move the session when enqueue fails', async () => {
    (enqueueAction as jest.Mock).mockResolvedValueOnce({
      success: false,
      data: { sessionId: null },
    });

    const { result } = renderHook(() => useChatSessionStream('session-1'));
    const fd = new FormData();
    fd.set('text', 'hello');

    await act(async () => {
      await result.current.submitAction(fd);
    });

    await waitFor(() => {
      expect(writeSessionMeta).not.toHaveBeenCalled();
      expect(modifySessionMeta).not.toHaveBeenCalled();
      expect(routerReplace).not.toHaveBeenCalled();
    });
  });

  it('adopts and routes immediately after enqueue succeeds for new session', async () => {
    pathname = '/chat';
    (enqueueAction as jest.Mock).mockResolvedValueOnce({
      success: true,
      data: { sessionId: 'session-new' },
    });

    const { result } = renderHook(() => useChatSessionStream(null));
    const fd = new FormData();
    fd.set('text', 'hello');

    await act(async () => {
      await result.current.submitAction(fd);
    });

    await waitFor(() => {
      expect(adoptNewSession).toHaveBeenCalledTimes(1);
      expect(adoptNewSession).toHaveBeenCalledWith('session-new');
      expect(routerReplace).toHaveBeenCalledWith('/chat/session-new', { scroll: false });
      expect(writeSessionMeta).not.toHaveBeenCalled();
      expect(modifySessionMeta).not.toHaveBeenCalled();
    });
  });

  it('does not route when enqueue fails for new session', async () => {
    pathname = '/chat';
    (enqueueAction as jest.Mock).mockResolvedValueOnce({
      success: false,
      data: { sessionId: null },
    });

    const { result } = renderHook(() => useChatSessionStream(null));
    const fd = new FormData();
    fd.set('text', 'hello');

    await act(async () => {
      await result.current.submitAction(fd);
    });

    await waitFor(() => {
      expect(adoptNewSession).not.toHaveBeenCalled();
      expect(routerReplace).not.toHaveBeenCalled();
    });
  });
});
