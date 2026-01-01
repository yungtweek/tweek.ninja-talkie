export const ToolEventStatus = {
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
} as const;

export const ToolCallEventType = {
  CALL_IN_PROGRESS: 'tool.call.in_progress',
  CALL_COMPLETED: 'tool.call.completed',
} as const;

export const ToolEventTypes = [...Object.values(ToolCallEventType)] as const;

export type ToolEventStatus = typeof ToolEventStatus[keyof typeof ToolEventStatus];
export type ToolCallEventType = typeof ToolCallEventType[keyof typeof ToolCallEventType];

export type ToolEventMeta = { status: ToolEventStatus };

export type ToolCallPayload = {
  tool?: string;
  callId?: string;
  attempt?: number;
  tookMs?: number | null;
  argsPreview?: string | null;
  resultPreview?: string | null;
};

export type ToolCallSnapshot = {
  tool?: string;
  attempt?: number;
  inProgress?: ToolCallPayload | null;
  completed?: ToolCallPayload | null;
};

export type ToolCallsSnapshot = {
  order?: string[];
  calls?: Record<string, ToolCallSnapshot>;
};

export const ToolEventMetaByType: Record<ToolCallEventType, ToolEventMeta> = {
  [ToolCallEventType.CALL_IN_PROGRESS]: { status: ToolEventStatus.IN_PROGRESS },
  [ToolCallEventType.CALL_COMPLETED]: { status: ToolEventStatus.COMPLETED },
};

export const getToolEventMeta = (eventType: string): ToolEventMeta | null =>
  ToolEventMetaByType[eventType as ToolCallEventType] ?? null;
