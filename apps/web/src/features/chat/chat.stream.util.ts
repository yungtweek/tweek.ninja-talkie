import type {
  RagEventMeta,
  RagEventPayload,
  ToolCallPayload,
  ToolEventMeta,
} from '@talkie/events-contracts';
import {
  RagEventTypes,
  ToolEventTypes,
  getRagEventMeta,
  getToolEventMeta,
} from '@talkie/events-contracts';

type StreamHandlers = {
  onText?: (chunk: string) => void;
  onSources?: (sources: unknown) => void;
  onRagSearch?: (meta: RagEventMeta, payload: RagEventPayload) => void;
  onToolCall?: (meta: ToolEventMeta, payload: ToolCallPayload) => void;
  onDone?: () => void;
  onError?: (err: unknown) => void;
};

export function openChatStream(jobId: string, handlers: StreamHandlers) {
  const es = new EventSource(`/api/chat/${jobId}`, { withCredentials: true });
  let textBuffer = '';
  let flushHandle: number | null = null;

  const flushText = () => {
    if (!textBuffer) return;
    const chunk = textBuffer;
    textBuffer = '';
    flushHandle = null;
    handlers.onText?.(chunk);
  };

  const scheduleFlush = () => {
    if (flushHandle !== null) return;
    flushHandle = requestAnimationFrame(flushText);
  };

  es.addEventListener('token', (e: MessageEvent) => {
    const d = JSON.parse(e.data);
    const chunk = d.text ?? d.content ?? '';
    if (chunk) {
      textBuffer += chunk;
      scheduleFlush();
    }
  });

  es.addEventListener('sources', (e: MessageEvent) => {
    try {
      const d = JSON.parse(e.data);
      handlers.onSources?.(d);
    } catch (err) {
      console.warn('[chat][sources] parse failed', err);
    }
  });

  for (const eventName of RagEventTypes) {
    const meta = getRagEventMeta(eventName);
    if (!meta) continue;
    es.addEventListener(eventName, (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        handlers.onRagSearch?.(meta, d);
      } catch (err) {
        console.warn(`[chat][${eventName}] parse failed`, err);
      }
    });
  }

  for (const eventName of ToolEventTypes) {
    const meta = getToolEventMeta(eventName);
    if (!meta) continue;
    es.addEventListener(eventName, (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data) as ToolCallPayload & {
          tool?: string;
          callId?: string;
          attempt?: number;
          tookMs?: number | null;
          argsPreview?: string | null;
          resultPreview?: string | null;
        };
        const payload: ToolCallPayload = {
          tool: d.tool,
          callId: d.callId,
          attempt: d.attempt,
          tookMs: d.tookMs,
          argsPreview: d.argsPreview,
          resultPreview: d.resultPreview,
        };
        handlers.onToolCall?.(meta, payload);
      } catch (err) {
        console.warn(`[chat][${eventName}] parse failed`, err);
      }
    });
  }

  es.addEventListener('done', () => {
    if (flushHandle !== null) {
      cancelAnimationFrame(flushHandle);
      flushHandle = null;
    }
    flushText();
    es.close();
    handlers.onDone?.();
  });

  es.addEventListener('error', e => {
    if (flushHandle !== null) {
      cancelAnimationFrame(flushHandle);
      flushHandle = null;
    }
    flushText();
    es.close();
    handlers.onError?.(e);
  });

  return es;
}
