import { z } from 'zod';

export const ChatMode = z.enum(['gen', 'rag']);

export const EnqueueInputZ = z.object({
  message: z.string().trim().min(1, 'message is required').max(4000),
  jobId: z.uuid(),
  sessionId: z.uuid().nullish(),
  mode: ChatMode.optional().default('gen'),
});

export type EnqueueInput = z.infer<typeof EnqueueInputZ>;

export const EnqueueOutputZ = z.object({
  sessionId: z.uuid(),
  jobId: z.uuid(),
});
export type EnqueueOutput = z.infer<typeof EnqueueOutputZ>;

export const ChatSessionZ = z.object({
  id: z.uuid(),
  title: z.string().optional().nullable(),
  createdAt: z.union([z.string(), z.date()]).optional().nullable(),
  updatedAt: z.union([z.string(), z.date()]).optional().nullable(),
  lastMessagePreview: z.union([z.string(), z.date()]).optional().nullable(),
  lastMessageAt: z.union([z.string(), z.date()]).optional().nullable(),
});
export type ChatSessionZod = z.infer<typeof ChatSessionZ>;

export const ChatMessageZ = z.object({
  id: z.string(),
  role: z.string(), // or z.enum(['user','assistant','system']) if you want to constrain
  content: z.string(),
  messageIndex: z.number().int(),
  turn: z.number().int(),
  sourcesJson: z.unknown().nullable().optional(),
});
export type ChatMessageZod = z.infer<typeof ChatMessageZ>;
