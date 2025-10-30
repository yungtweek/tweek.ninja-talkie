import { z } from 'zod';

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
