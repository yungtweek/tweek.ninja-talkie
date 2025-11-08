type StreamHandlers = {
  onText?: (chunk: string) => void;
  onDone?: () => void;
  onError?: (err: unknown) => void;
};

export function openChatStream(jobId: string, handlers: StreamHandlers) {
  const es = new EventSource(`/api/chat/${jobId}`, { withCredentials: true });

  es.addEventListener('token', (e: MessageEvent) => {
    const d = JSON.parse(e.data);
    const chunk = d.text ?? d.content ?? '';
    if (chunk) {
      handlers.onText?.(chunk);
    }
  });

  es.addEventListener('done', () => {
    es.close();
    handlers.onDone?.();
  });

  es.addEventListener('error', e => {
    es.close();
    handlers.onError?.(e);
  });

  return es;
}
