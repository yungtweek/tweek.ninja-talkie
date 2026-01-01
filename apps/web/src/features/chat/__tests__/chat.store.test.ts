import { chatStore, selectIsStreaming } from '@/features/chat/chat.store';
import type { ChatEdge } from '@/features/chat/chat.types';
import { safeJsonParse } from '@/lib/utils';
import {
  RagEventMetaByType,
  RagStageEventType,
  ToolCallEventType,
  ToolEventMetaByType,
  ToolCallsSnapshot,
} from '@talkie/events-contracts';

const baseState = chatStore.getState();

afterEach(() => {
  chatStore.setState({ ...baseState, edges: [] });
});

describe('selectIsStreaming', () => {
  it('returns false when there are no edges', () => {
    const edges: ChatEdge[] = [];
    expect(selectIsStreaming(edges)).toBe(false);
  });

  it('returns false when assistant stream is done', () => {
    const edges: ChatEdge[] = [
      { node: { role: 'assistant', content: 'hi', streamDone: true } },
    ];
    expect(selectIsStreaming(edges)).toBe(false);
  });

  it('returns true when assistant stream is active', () => {
    const edges: ChatEdge[] = [
      { node: { role: 'assistant', content: '', streamDone: false } },
    ];
    expect(selectIsStreaming(edges)).toBe(true);
  });

  it('ignores non-assistant roles', () => {
    const edges: ChatEdge[] = [
      { node: { role: 'user', content: 'hi', streamDone: false } },
    ];
    expect(selectIsStreaming(edges)).toBe(false);
  });
});

describe('updateRagSearch', () => {
  it('keeps in-progress and completed snapshots for detail view', () => {
    const jobId = 'job-123';
    chatStore.setState({
      ...baseState,
      edges: [
        {
          node: {
            role: 'assistant',
            content: '',
            jobId,
            ragSearchJson: JSON.stringify({
              stages: {
                retrieve: {
                  inProgress: {
                    query: 'hello',
                    hits: 1,
                  },
                  completed: null,
                },
              },
            }),
          },
        },
      ],
    });

    chatStore.getState().updateRagSearch(
      jobId,
      RagEventMetaByType[RagStageEventType.RETRIEVE_COMPLETED],
      { hits: 2, tookMs: 15 },
    );

    const updated = safeJsonParse<{
      stages?: {
        retrieve?: {
          inProgress?: { query?: string; hits?: number } | null;
          completed?: { hits?: number; tookMs?: number } | null;
        } | null;
      } | null;
    }>(chatStore.getState().edges[0]?.node.ragSearchJson, null);
    expect(updated).toEqual({
      wrapper: {},
      stages: {
        retrieve: {
          inProgress: {
            query: 'hello',
            hits: 1,
          },
          completed: {
            hits: 2,
            tookMs: 15,
          },
        },
      },
    });
  });
});

describe('updateToolCalls', () => {
  it('tracks tool call progress and completion', () => {
    const jobId = 'job-999';
    chatStore.setState({
      ...baseState,
      edges: [
        {
          node: {
            role: 'assistant',
            content: '',
            jobId,
          },
        },
      ],
    });

    chatStore.getState().updateToolCalls(
      jobId,
      ToolEventMetaByType[ToolCallEventType.CALL_IN_PROGRESS],
      {
        tool: 'search',
        callId: 'call-1',
        attempt: 1,
        argsPreview: '{"q":"hi"}',
      },
    );

    chatStore.getState().updateToolCalls(
      jobId,
      ToolEventMetaByType[ToolCallEventType.CALL_COMPLETED],
      {
        tool: 'search',
        callId: 'call-1',
        attempt: 1,
        tookMs: 120,
        resultPreview: '{"ok":true}',
      },
    );

    const updated = safeJsonParse<ToolCallsSnapshot>(
      chatStore.getState().edges[0]?.node.toolCallsJson,
      null,
    );
    expect(updated).toEqual({
      order: ['call-1'],
      calls: {
        'call-1': {
          tool: 'search',
          attempt: 1,
          inProgress: {
            tool: 'search',
            callId: 'call-1',
            attempt: 1,
            argsPreview: '{"q":"hi"}',
          },
          completed: {
            tool: 'search',
            callId: 'call-1',
            attempt: 1,
            tookMs: 120,
            resultPreview: '{"ok":true}',
          },
        },
      },
    });
  });
});
