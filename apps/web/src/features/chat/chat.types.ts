import type {
  RagEventMeta,
  RagEventPayload,
  RagEventStatus,
  RagSearchSnapshot,
  RagSearchKey,
  RagStageKey,
  RagStagePayload,
  RagStageSnapshot,
  RagWrapperKey,
  RagWrapperSnapshot,
  ToolCallPayload,
  ToolCallSnapshot,
  ToolCallsSnapshot,
  ToolEventMeta,
  ToolEventStatus,
} from '@talkie/events-contracts';

export type Role = 'user' | 'assistant' | 'system';

export type {
  RagEventMeta,
  RagEventPayload,
  RagEventStatus,
  RagSearchSnapshot,
  RagSearchKey,
  RagStageKey,
  RagStagePayload,
  RagStageSnapshot,
  RagWrapperKey,
  RagWrapperSnapshot,
  ToolCallPayload,
  ToolCallSnapshot,
  ToolCallsSnapshot,
  ToolEventMeta,
  ToolEventStatus,
};

export type RagLiveEvent = {
  meta: RagEventMeta;
  payload?: RagEventPayload;
};


export interface ChatEdge {
  cursor?: string | null;
  node: ChatNode;
}

export interface ChatNode {
  id?: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  messageIndex?: number | null;
  turn?: number | null;
  sourcesJson?: string | null;
  ragSearchJson?: string | null;
  toolCallsJson?: string | null;
  jobId?: string | null;
  streamDone?: boolean;
  ragSearch?: RagLiveEvent;
}
