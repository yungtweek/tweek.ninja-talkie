// apps/gateway/src/modules/chat/dto/enqueue.zod.ts
import { z } from 'zod';

export const ChatMode = z.enum(['gen', 'rag']);

export const EnqueueSchema = z.object({
  message: z.string().trim().min(1, 'message is required').max(4000),
  jobId: z.uuid(),
  sessionId: z.uuid().nullish(),
  mode: ChatMode.optional().default('gen'),
});

export type EnqueueInput = z.infer<typeof EnqueueSchema>;
