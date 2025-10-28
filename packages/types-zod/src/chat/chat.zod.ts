import {z} from 'zod';

export const ChatSessionsZ = z.object({
    id: z.uuid(),
    title: z.string().optional().nullable(),
    createdAt: z.union([z.string(), z.date()]).optional().nullable(),
    updatedAt: z.union([z.string(), z.date()]).optional().nullable(),
    lastMessagePreview: z.union([z.string(), z.date()]).optional().nullable(),
    lastMessageAt: z.union([z.string(), z.date()]).optional().nullable(),
});
export type ChatSessionsZod = z.infer<typeof ChatSessionsZ>;


// Connection 형태가 필요할 때를 위한 보조 스키마 (선택)
export const ChatSessionsEdgeZ = z.object({
    cursor: z.string(),
    node: ChatSessionsZ,
});
export const PageInfoZ = z.object({
    endCursor: z.string().optional(),
    hasNextPage: z.boolean(),
});
export const ChatSessionsConnectionZ = z.object({
    edges: z.array(ChatSessionsEdgeZ),
    pageInfo: PageInfoZ,
});
export type ChatSessionsEdgeZod = z.infer<typeof ChatSessionsEdgeZ>;
export type ChatSessionsConnectionZod = z.infer<typeof ChatSessionsConnectionZ>;
export type PageInfoZod = z.infer<typeof PageInfoZ>;


export const ChatMessageZ = z.object({
    id: z.string(),
    role: z.string(), // or z.enum(['user','assistant','system']) if you want to constrain
    content: z.string(),
    messageIndex: z.number().int(),
    turn: z.number().int(),
    sourcesJson: z.unknown().nullable().optional(),
})
export type ChatMessageZod = z.infer<typeof ChatSessionsZ>;
